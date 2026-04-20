"""Invoices API."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ApproveRejectRequest,
    BulkActionFailure,
    BulkActionRequest,
    BulkActionResponse,
    CsvImportResult,
    InvoiceCreate,
    InvoiceListResponse,
    InvoiceResponse,
    SendInvoiceRequest,
)
from app.infra.models import Account, Contact, Invoice
from app.services.csv_import import generate_template_csv, parse_csv, parse_date, parse_decimal
from app.services.email_service import send_email
from app.services.invoices import (
    ArchivedContactError,
    CreditLimitExceededError,
    InvalidAccountError,
    InvoiceApprovalError,
    InvoiceNotFoundError,
    InvoiceTransitionError,
    approve_invoice,
    authorise_invoice,
    create_credit_note,  # noqa: F401 — re-exported; void_invoice calls it internally
    create_invoice,
    get_invoice,
    get_invoice_lines,
    list_invoices,
    send_invoice,
    void_invoice,
)
from app.services.tax_codes import TaxCodeNotFoundError, get_tax_code
from app.workers.reminders import _build_reminder_html

router = APIRouter(prefix="/invoices", tags=["invoices"])


async def _resolve_line_tax(db, tenant_id: str, lines: list) -> list[dict]:
    """Add _tax_rate to each line dict by looking up tax_code_id."""
    resolved = []
    for line in lines:
        d = line.model_dump()
        d["quantity"] = Decimal(d["quantity"])
        d["unit_price"] = Decimal(d["unit_price"])
        d["discount_pct"] = Decimal(d["discount_pct"])
        if d.get("tax_code_id"):
            try:
                tc = await get_tax_code(db, tenant_id, d["tax_code_id"])
                d["_tax_rate"] = Decimal(str(tc.rate))
            except TaxCodeNotFoundError:
                d["_tax_rate"] = Decimal("0")
        else:
            d["_tax_rate"] = Decimal("0")
        resolved.append(d)
    return resolved


async def _invoice_response(db, inv) -> InvoiceResponse:
    lines = await get_invoice_lines(db, inv.id)
    return InvoiceResponse.model_validate({**inv.__dict__, "lines": lines})


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create(body: InvoiceCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    lines = await _resolve_line_tax(db, tenant_id, body.lines)
    try:
        inv = await create_invoice(
            db,
            tenant_id,
            actor_id,
            contact_id=body.contact_id,
            issue_date=str(body.issue_date),
            due_date=str(body.due_date) if body.due_date else None,
            currency=body.currency,
            fx_rate=Decimal(body.fx_rate),
            period_name=body.period_name,
            reference=body.reference,
            notes=body.notes,
            lines=lines,
        )
    except (InvalidAccountError, ArchivedContactError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(inv)
    return await _invoice_response(db, inv)


@router.get("", response_model=InvoiceListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    inv_status: str | None = Query(default=None, alias="status"),
    contact_id: str | None = Query(default=None),
    due_before: str | None = Query(default=None, description="Filter: due_date <= this date"),
    due_after: str | None = Query(default=None, description="Filter: due_date >= this date"),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_invoices(
        db,
        tenant_id,
        status=inv_status,
        contact_id=contact_id,
        due_before=due_before,
        due_after=due_after,
        limit=limit + 1,
        cursor=cursor,
    )
    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit].id
        items = items[:limit]
    result = []
    for inv in items:
        lines = await get_invoice_lines(db, inv.id)
        result.append(InvoiceResponse.model_validate({**inv.__dict__, "lines": lines}))
    return InvoiceListResponse(items=result, next_cursor=next_cursor)


@router.post("/bulk/authorise", response_model=BulkActionResponse)
async def bulk_authorise(
    body: BulkActionRequest, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> BulkActionResponse:
    """Authorise multiple draft invoices. Processes all items; does not fail-fast."""
    succeeded: list[str] = []
    failed: list[BulkActionFailure] = []
    for inv_id in body.ids:
        try:
            await authorise_invoice(db, tenant_id, inv_id, actor_id)
            succeeded.append(inv_id)
        except Exception as exc:
            failed.append(BulkActionFailure(id=inv_id, error=str(exc)))
    await db.commit()
    return BulkActionResponse(succeeded=succeeded, failed=failed)


@router.post("/bulk/void", response_model=BulkActionResponse)
async def bulk_void(
    body: BulkActionRequest, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> BulkActionResponse:
    """Void multiple invoices. Processes all items; does not fail-fast."""
    succeeded: list[str] = []
    failed: list[BulkActionFailure] = []
    for inv_id in body.ids:
        try:
            await void_invoice(db, tenant_id, inv_id, actor_id)
            succeeded.append(inv_id)
        except Exception as exc:
            failed.append(BulkActionFailure(id=inv_id, error=str(exc)))
    await db.commit()
    return BulkActionResponse(succeeded=succeeded, failed=failed)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_one(invoice_id: str, db: DbSession, tenant_id: TenantId):
    try:
        inv = await get_invoice(db, tenant_id, invoice_id)
        return await _invoice_response(db, inv)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")


@router.post("/{invoice_id}/authorise", response_model=InvoiceResponse)
async def authorise(
    invoice_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    force: bool = Query(default=False),
):
    try:
        inv = await authorise_invoice(db, tenant_id, invoice_id, actor_id, force=force)
        await db.commit()
        await db.refresh(inv)
        return await _invoice_response(db, inv)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    except CreditLimitExceededError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except InvoiceTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{invoice_id}/approve", response_model=InvoiceResponse)
async def approve(
    invoice_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    body: ApproveRejectRequest | None = None,
):
    try:
        comment = body.comment if body else None
        inv = await approve_invoice(db, tenant_id, invoice_id, actor_id, comment=comment)
        await db.commit()
        await db.refresh(inv)
        return await _invoice_response(db, inv)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    except InvoiceApprovalError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))
    except InvoiceTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{invoice_id}/void", response_model=InvoiceResponse)
async def void(invoice_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        inv = await void_invoice(db, tenant_id, invoice_id, actor_id)
        await db.commit()
        await db.refresh(inv)
        return await _invoice_response(db, inv)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    except InvoiceTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/{invoice_id}/pdf")
async def download_pdf(invoice_id: str, db: DbSession, tenant_id: TenantId) -> Response:
    """Generate and return a branded PDF for the invoice."""
    from sqlalchemy import select

    from app.infra.models import Tenant
    from app.infra.pdf import render_invoice_pdf
    from app.services.invoices import get_contact as _get_contact

    try:
        inv = await get_invoice(db, tenant_id, invoice_id)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    lines = await get_invoice_lines(db, inv.id)

    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    tenant_name = getattr(tenant, "name", None) or "Your Company"

    contact_display: str | None = None
    try:
        contact = await _get_contact(db, tenant_id, inv.contact_id)
        contact_display = getattr(contact, "name", None)
    except ValueError:
        contact_display = None

    try:
        pdf_bytes = render_invoice_pdf(
            inv, lines, tenant_name=tenant_name, contact_display=contact_display
        )
    except RuntimeError as exc:  # fpdf2 missing
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice-{inv.number}.pdf"',
        },
    )


@router.post("/{invoice_id}/send", response_model=InvoiceResponse)
async def send(
    invoice_id: str,
    body: SendInvoiceRequest,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
):
    """Send an invoice via email with a branded PDF attached.

    On success the invoice transitions to ``sent`` (from ``authorised``) and
    an ``invoice.sent`` audit event is emitted with the recipient address.
    """
    try:
        inv = await send_invoice(
            db,
            tenant_id,
            invoice_id,
            to=body.to,
            subject=body.subject,
            message=body.message,
            actor_id=actor_id,
        )
        await db.commit()
        await db.refresh(inv)
        return await _invoice_response(db, inv)
    except InvoiceNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    except InvoiceTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{invoice_id}/reminder", status_code=status.HTTP_202_ACCEPTED)
async def send_reminder(invoice_id: str, db: DbSession, tenant_id: TenantId):
    """Manually trigger a payment reminder for a single invoice."""
    # Load invoice scoped to tenant
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    # Load contact
    contact_result = await db.execute(
        select(Contact).where(Contact.id == inv.contact_id, Contact.tenant_id == tenant_id)
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None or not contact.email:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contact has no email address",
        )

    from datetime import date as _date  # noqa: PLC0415

    due_date_str = str(inv.due_date) if inv.due_date else "N/A"
    if inv.due_date:
        days_overdue = (_date.today() - _date.fromisoformat(str(inv.due_date))).days
    else:
        days_overdue = 0

    html = _build_reminder_html(
        contact_name=contact.name,
        invoice_number=inv.number,
        due_date=due_date_str,
        amount_due=str(inv.amount_due),
        currency=inv.currency,
        days_overdue=days_overdue,
    )
    ok = await send_email(
        to=contact.email,
        subject=f"Payment Reminder: Invoice {inv.number}",
        html=html,
    )
    if ok:
        inv.last_reminder_sent_at = datetime.now(tz=UTC)
        inv.reminder_count = (inv.reminder_count or 0) + 1
        await db.commit()

    return {"sent": ok}


# ── CSV Import / Template ────────────────────────────────────────────────────

_INVOICE_REQUIRED = ["contact_name_or_code", "issue_date", "account_code", "quantity", "unit_price"]
_INVOICE_OPTIONAL = [
    "due_date",
    "currency",
    "description",
    "tax_code",
    "discount_pct",
    "reference",
]
_INVOICE_ALL = _INVOICE_REQUIRED + _INVOICE_OPTIONAL
_INVOICE_EXAMPLE = [
    "Acme Corp",
    "2025-01-15",
    "4000",
    "1",
    "1000.00",
    "2025-02-15",
    "USD",
    "Consulting services",
    "",
    "0",
    "INV-001",
]


@router.get("/csv-template")
async def csv_template() -> StreamingResponse:
    """Download a CSV template for invoice imports."""
    content = generate_template_csv(_INVOICE_ALL, _INVOICE_EXAMPLE)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="invoices-template.csv"'},
    )


@router.post("/import", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
async def import_invoices(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> CsvImportResult:
    """Import invoices from a CSV file.

    Rows with same contact_name_or_code + issue_date + reference are grouped
    into one invoice with multiple lines.
    """
    content = await file.read()
    rows, errors = await parse_csv(content, _INVOICE_REQUIRED, _INVOICE_OPTIONAL)

    if errors and not rows:
        return CsvImportResult(imported=0, skipped=0, errors=errors)

    # Resolve contacts: name or code -> id
    contact_result = await db.execute(
        select(Contact.id, Contact.name, Contact.code).where(
            Contact.tenant_id == tenant_id, Contact.is_archived.is_(False)
        )
    )
    contact_map: dict[str, str] = {}
    for cid, cname, ccode in contact_result:
        contact_map[cname.lower()] = cid
        if ccode:
            contact_map[ccode.lower()] = cid

    # Resolve accounts: code -> id
    acct_result = await db.execute(
        select(Account.id, Account.code).where(Account.tenant_id == tenant_id)
    )
    acct_map: dict[str, str] = {code.lower(): aid for aid, code in acct_result}

    # Group rows into invoices
    groups: dict[tuple[str, str, str], list[tuple[int, dict[str, str]]]] = {}
    for row_no, row in enumerate(rows, start=2 + len(errors)):
        key = (
            row["contact_name_or_code"].lower(),
            row["issue_date"],
            row.get("reference", ""),
        )
        groups.setdefault(key, []).append((row_no, row))

    imported = 0
    skipped = 0

    for (contact_key, issue_date_str, reference), group_rows in groups.items():
        try:
            contact_id = contact_map.get(contact_key)
            if not contact_id:
                for row_no, _ in group_rows:
                    errors.append(f"Row {row_no}: contact '{contact_key}' not found")
                skipped += len(group_rows)
                continue

            parsed_issue = parse_date(issue_date_str)
            first_row = group_rows[0][1]
            currency = first_row.get("currency") or "USD"
            due_date_str = first_row.get("due_date")
            parsed_due = str(parse_date(due_date_str)) if due_date_str else None

            lines: list[dict] = []
            line_error = False
            for row_no, row in group_rows:
                acct_code = row["account_code"].lower()
                acct_id = acct_map.get(acct_code)
                if not acct_id:
                    errors.append(f"Row {row_no}: account_code '{row['account_code']}' not found")
                    line_error = True
                    continue

                qty = parse_decimal(row["quantity"])
                price = parse_decimal(row["unit_price"])
                discount = parse_decimal(row.get("discount_pct") or "0")

                lines.append(
                    {
                        "account_id": acct_id,
                        "description": row.get("description") or None,
                        "quantity": qty,
                        "unit_price": price,
                        "discount_pct": discount,
                        "_tax_rate": Decimal("0"),
                    }
                )

            if line_error or not lines:
                skipped += len(group_rows)
                continue

            await create_invoice(
                db,
                tenant_id,
                actor_id,
                contact_id=contact_id,
                issue_date=str(parsed_issue),
                due_date=parsed_due,
                currency=currency,
                reference=reference or None,
                lines=lines,
            )
            imported += 1
        except Exception as exc:
            for row_no, _ in group_rows:
                errors.append(f"Row {row_no}: {exc}")
            skipped += 1

    if imported > 0:
        await db.commit()

    from app.core.logging import get_logger

    get_logger(__name__).info(
        "invoices.import.complete",
        tenant_id=tenant_id,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return CsvImportResult(imported=imported, skipped=skipped, errors=errors)
