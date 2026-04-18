"""Bills API."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.v1.deps import ActorId, DbSession, TenantId
from app.api.v1.schemas import (
    ApproveRejectRequest,
    BillCreate,
    BillListResponse,
    BillResponse,
    BulkActionFailure,
    BulkActionRequest,
    BulkActionResponse,
    CsvImportResult,
)
from app.infra.models import Account, Contact
from app.services.bills import (
    ArchivedContactError,
    BillNotFoundError,
    BillTransitionError,
    InvalidAccountError,
    approve_bill,
    create_bill,
    get_bill,
    get_bill_lines,
    list_bills,
    submit_for_approval,
    void_bill,
)
from app.services.csv_import import generate_template_csv, parse_csv, parse_date, parse_decimal
from app.services.tax_codes import TaxCodeNotFoundError, get_tax_code

router = APIRouter(prefix="/bills", tags=["bills"])


async def _resolve_line_tax(db, tenant_id: str, lines: list) -> list[dict]:
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


async def _bill_response(db, bill) -> BillResponse:
    lines = await get_bill_lines(db, bill.id)
    return BillResponse.model_validate({**bill.__dict__, "lines": lines})


@router.post("", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
async def create(body: BillCreate, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    lines = await _resolve_line_tax(db, tenant_id, body.lines)
    try:
        bill = await create_bill(
            db,
            tenant_id,
            actor_id,
            contact_id=body.contact_id,
            issue_date=str(body.issue_date),
            due_date=str(body.due_date) if body.due_date else None,
            currency=body.currency,
            fx_rate=Decimal(body.fx_rate),
            period_name=body.period_name,
            supplier_reference=body.supplier_reference,
            notes=body.notes,
            lines=lines,
        )
    except (InvalidAccountError, ArchivedContactError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(bill)
    return await _bill_response(db, bill)


@router.get("", response_model=BillListResponse)
async def list_all(
    db: DbSession,
    tenant_id: TenantId,
    bill_status: str | None = Query(default=None, alias="status"),
    contact_id: str | None = Query(default=None),
    due_before: str | None = Query(default=None, description="Filter: due_date <= this date"),
    due_after: str | None = Query(default=None, description="Filter: due_date >= this date"),
    limit: int = Query(default=50, le=200),
    cursor: str | None = Query(default=None),
):
    items = await list_bills(
        db,
        tenant_id,
        status=bill_status,
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
    for bill in items:
        lines = await get_bill_lines(db, bill.id)
        result.append(BillResponse.model_validate({**bill.__dict__, "lines": lines}))
    return BillListResponse(items=result, next_cursor=next_cursor)


@router.post("/bulk/approve", response_model=BulkActionResponse)
async def bulk_approve(
    body: BulkActionRequest, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> BulkActionResponse:
    """Approve multiple bills. Processes all items; does not fail-fast."""
    succeeded: list[str] = []
    failed: list[BulkActionFailure] = []
    for bill_id in body.ids:
        try:
            await approve_bill(db, tenant_id, bill_id, actor_id)
            succeeded.append(bill_id)
        except Exception as exc:
            failed.append(BulkActionFailure(id=bill_id, error=str(exc)))
    await db.commit()
    return BulkActionResponse(succeeded=succeeded, failed=failed)


@router.post("/bulk/void", response_model=BulkActionResponse)
async def bulk_void(
    body: BulkActionRequest, db: DbSession, tenant_id: TenantId, actor_id: ActorId
) -> BulkActionResponse:
    """Void multiple bills. Processes all items; does not fail-fast."""
    succeeded: list[str] = []
    failed: list[BulkActionFailure] = []
    for bill_id in body.ids:
        try:
            await void_bill(db, tenant_id, bill_id, actor_id)
            succeeded.append(bill_id)
        except Exception as exc:
            failed.append(BulkActionFailure(id=bill_id, error=str(exc)))
    await db.commit()
    return BulkActionResponse(succeeded=succeeded, failed=failed)


@router.get("/{bill_id}", response_model=BillResponse)
async def get_one(bill_id: str, db: DbSession, tenant_id: TenantId):
    try:
        bill = await get_bill(db, tenant_id, bill_id)
        return await _bill_response(db, bill)
    except BillNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bill not found")


@router.post("/{bill_id}/submit", response_model=BillResponse)
async def submit(bill_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        bill = await submit_for_approval(db, tenant_id, bill_id, actor_id)
        await db.commit()
        await db.refresh(bill)
        return await _bill_response(db, bill)
    except BillNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bill not found")
    except BillTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{bill_id}/approve", response_model=BillResponse)
async def approve(
    bill_id: str,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
    body: ApproveRejectRequest | None = None,
):
    try:
        comment = body.comment if body else None
        bill = await approve_bill(db, tenant_id, bill_id, actor_id, comment=comment)
        await db.commit()
        await db.refresh(bill)
        return await _bill_response(db, bill)
    except BillNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bill not found")
    except BillTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{bill_id}/void", response_model=BillResponse)
async def void(bill_id: str, db: DbSession, tenant_id: TenantId, actor_id: ActorId):
    try:
        bill = await void_bill(db, tenant_id, bill_id, actor_id)
        await db.commit()
        await db.refresh(bill)
        return await _bill_response(db, bill)
    except BillNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bill not found")
    except BillTransitionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


# ── CSV Import / Template ────────────────────────────────────────────────────

_BILL_REQUIRED = ["contact_name_or_code", "issue_date", "account_code", "quantity", "unit_price"]
_BILL_OPTIONAL = [
    "due_date", "currency", "description", "tax_code", "discount_pct", "reference",
]
_BILL_ALL = _BILL_REQUIRED + _BILL_OPTIONAL
_BILL_EXAMPLE = [
    "Office Depot", "2025-01-10", "6300", "1", "500.00",
    "2025-02-10", "USD", "Office supplies", "", "0", "BILL-001",
]


@router.get("/csv-template")
async def csv_template() -> StreamingResponse:
    """Download a CSV template for bill imports."""
    content = generate_template_csv(_BILL_ALL, _BILL_EXAMPLE)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="bills-template.csv"'},
    )


@router.post("/import", response_model=CsvImportResult, status_code=status.HTTP_201_CREATED)
async def import_bills(
    file: UploadFile,
    db: DbSession,
    tenant_id: TenantId,
    actor_id: ActorId,
) -> CsvImportResult:
    """Import bills from a CSV file.

    Rows with same contact_name_or_code + issue_date + reference are grouped
    into one bill with multiple lines.
    """
    content = await file.read()
    rows, errors = await parse_csv(content, _BILL_REQUIRED, _BILL_OPTIONAL)

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

    # Group rows into bills
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

                lines.append({
                    "account_id": acct_id,
                    "description": row.get("description") or None,
                    "quantity": qty,
                    "unit_price": price,
                    "discount_pct": discount,
                    "_tax_rate": Decimal("0"),
                })

            if line_error or not lines:
                skipped += len(group_rows)
                continue

            await create_bill(
                db,
                tenant_id,
                actor_id,
                contact_id=contact_id,
                issue_date=str(parsed_issue),
                due_date=parsed_due,
                currency=currency,
                supplier_reference=reference or None,
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
        "bills.import.complete",
        tenant_id=tenant_id,
        imported=imported,
        skipped=skipped,
        errors=len(errors),
    )
    return CsvImportResult(imported=imported, skipped=skipped, errors=errors)
