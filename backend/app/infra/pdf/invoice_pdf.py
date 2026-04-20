"""Render an ``Invoice`` and its lines to a branded PDF (fpdf2).

This module intentionally takes plain objects / simple attributes so it can
be called by services and workers, not just the API layer. It does not
touch the database.
"""

from __future__ import annotations

from typing import Any, Protocol


class _InvoiceLike(Protocol):
    id: str
    number: str
    contact_id: str
    currency: str
    subtotal: Any
    tax_total: Any
    total: Any
    status: str
    issue_date: Any
    due_date: Any


class _LineLike(Protocol):
    description: str | None
    quantity: Any
    unit_price: Any
    line_amount: Any


def render_invoice_pdf(
    inv: _InvoiceLike,
    lines: list[_LineLike],
    *,
    tenant_name: str = "Your Company",
    contact_display: str | None = None,
    footer_message: str = "Thank you for your business.",
) -> bytes:
    """Render an invoice to PDF bytes. Layout is fixed; CLAUDE.md §16
    ``make openapi`` has no interaction with this renderer.

    Args:
        inv: The invoice record (must expose ``number``, ``currency``,
            ``subtotal``, ``tax_total``, ``total``, ``status``, ``issue_date``,
            ``due_date``, ``contact_id``).
        lines: Invoice lines.
        tenant_name: Printed under the ``INVOICE`` header.
        contact_display: Printed in the BILL TO block. Defaults to the first
            36 characters of ``inv.contact_id`` when not supplied.
    """
    try:
        from fpdf import FPDF  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("fpdf2 is required for invoice PDF rendering") from exc

    bill_to = contact_display or (inv.contact_id[:36] if inv.contact_id else "")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 12, "INVOICE", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, tenant_name, ln=True, align="C")
    pdf.ln(4)

    # Meta block
    pdf.set_draw_color(200, 200, 200)
    pdf.set_fill_color(245, 245, 250)
    pdf.rect(10, pdf.get_y(), 190, 28, style="F")
    y_meta = pdf.get_y() + 5

    pdf.set_xy(15, y_meta)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(90, 5, "BILL TO", ln=False)

    pdf.set_xy(110, y_meta)
    pdf.cell(45, 5, "Invoice #:", ln=False)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, inv.number, ln=True)

    pdf.set_xy(15, y_meta + 6)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(90, 5, bill_to, ln=False)

    pdf.set_xy(110, y_meta + 6)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(45, 5, "Issue Date:", ln=False)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 5, str(inv.issue_date), ln=True)

    if inv.due_date:
        pdf.set_xy(110, y_meta + 12)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(45, 5, "Due Date:", ln=False)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 5, str(inv.due_date), ln=True)

    pdf.set_xy(110, y_meta + (18 if inv.due_date else 12))
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(45, 5, "Status:", ln=False)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 5, inv.status.upper(), ln=True)

    pdf.set_y(y_meta + 33)
    pdf.ln(2)

    # Line items table header
    pdf.set_fill_color(40, 40, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    col_w = [90, 25, 35, 35]
    headers = ["Description", "Qty", "Unit Price", "Amount"]
    for h, w in zip(headers, col_w, strict=False):
        pdf.cell(w, 7, h, border=0, fill=True, align="C" if h != "Description" else "L")
    pdf.ln()

    # Line items
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "", 9)
    fill = False
    for line in lines:
        if fill:
            pdf.set_fill_color(248, 248, 252)
        else:
            pdf.set_fill_color(255, 255, 255)
        desc = (line.description or "")[:60]
        pdf.cell(col_w[0], 6, desc, border=0, fill=True)
        pdf.cell(col_w[1], 6, str(line.quantity), border=0, fill=True, align="C")
        pdf.cell(col_w[2], 6, f"{inv.currency} {line.unit_price}", border=0, fill=True, align="R")
        pdf.cell(col_w[3], 6, f"{inv.currency} {line.line_amount}", border=0, fill=True, align="R")
        pdf.ln()
        fill = not fill

    pdf.ln(2)

    def _total_row(label: str, value: str) -> None:
        pdf.set_x(120)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(45, 6, label, align="R")
        pdf.set_text_color(30, 30, 30)
        pdf.cell(30, 6, f"{inv.currency} {value}", align="R")
        pdf.ln()

    pdf.set_draw_color(200, 200, 200)
    pdf.set_x(120)
    pdf.cell(75, 0.5, "", border="T")
    pdf.ln(2)

    _total_row("Subtotal:", str(inv.subtotal))
    _total_row("Tax:", str(inv.tax_total))

    pdf.set_x(120)
    pdf.set_fill_color(40, 40, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(45, 8, "TOTAL:", align="R", fill=True)
    pdf.cell(30, 8, f"{inv.currency} {inv.total}", align="R", fill=True)
    pdf.ln(10)

    # Footer
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 6, footer_message, align="C")

    # fpdf2 returns bytearray in newer versions; normalize to bytes.
    out = pdf.output()
    return bytes(out)
