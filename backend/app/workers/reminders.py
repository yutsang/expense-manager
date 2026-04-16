"""ARQ worker: daily overdue invoice reminders."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger

log = get_logger(__name__)

# Don't send more than one reminder per invoice per N days
_MIN_REMINDER_INTERVAL_DAYS = 3


async def send_overdue_reminders(ctx: dict[str, Any]) -> dict[str, Any]:
    """Find overdue invoices and send reminder emails to contacts."""
    from app.infra.models import Contact, Invoice  # noqa: PLC0415
    from app.services.email_service import send_email  # noqa: PLC0415

    today = date.today().isoformat()
    sent = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Invoice, Contact)
            .join(Contact, Contact.id == Invoice.contact_id)
            .where(
                Invoice.due_date < today,
                Invoice.status.in_(["sent", "partial"]),
                Invoice.amount_due > 0,
            )
        )
        rows = result.all()

        for invoice, contact in rows:
            # Skip if reminded recently
            if invoice.last_reminder_sent_at:
                days_since = (datetime.now(tz=timezone.utc) - invoice.last_reminder_sent_at).days
                if days_since < _MIN_REMINDER_INTERVAL_DAYS:
                    skipped += 1
                    continue

            if not contact.email:
                skipped += 1
                continue

            days_overdue = (date.today() - date.fromisoformat(str(invoice.due_date))).days
            html = _build_reminder_html(
                contact_name=contact.name,
                invoice_number=invoice.number,
                due_date=str(invoice.due_date),
                amount_due=str(invoice.amount_due),
                currency=invoice.currency,
                days_overdue=days_overdue,
            )
            ok = await send_email(
                to=contact.email,
                subject=f"Payment Reminder: Invoice {invoice.number} is {days_overdue} days overdue",
                html=html,
            )
            if ok:
                invoice.last_reminder_sent_at = datetime.now(tz=timezone.utc)
                invoice.reminder_count = (invoice.reminder_count or 0) + 1
                sent += 1

        await db.commit()

    log.info("reminders.done", sent=sent, skipped=skipped)
    return {"sent": sent, "skipped": skipped}


def _build_reminder_html(
    *,
    contact_name: str,
    invoice_number: str,
    due_date: str,
    amount_due: str,
    currency: str,
    days_overdue: int,
) -> str:
    plural = "s" if days_overdue != 1 else ""
    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px">
      <h2 style="color:#dc2626">Payment Overdue</h2>
      <p>Dear {contact_name},</p>
      <p>This is a reminder that the following invoice is now <strong>{days_overdue} day{plural} overdue</strong>:</p>
      <table style="border-collapse:collapse;width:100%;margin:16px 0">
        <tr><td style="padding:8px;border:1px solid #e5e7eb;color:#6b7280">Invoice Number</td>
            <td style="padding:8px;border:1px solid #e5e7eb;font-weight:600">{invoice_number}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e5e7eb;color:#6b7280">Due Date</td>
            <td style="padding:8px;border:1px solid #e5e7eb">{due_date}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e5e7eb;color:#6b7280">Amount Due</td>
            <td style="padding:8px;border:1px solid #e5e7eb;font-weight:600;color:#dc2626">{currency} {amount_due}</td></tr>
      </table>
      <p>Please arrange payment at your earliest convenience.</p>
      <p style="color:#6b7280;font-size:12px">This is an automated reminder from Aegis ERP.</p>
    </div>
    """
