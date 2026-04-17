"""Management accounts PDF — combined P&L + Balance Sheet + Cash Flow (Issue #45).

Generates a single PDF with consistent branding using fpdf2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF


class _MgmtAccountsPDF(FPDF):
    """Custom FPDF subclass with header/footer for management accounts."""

    def __init__(self, company_name: str, period_label: str) -> None:
        super().__init__()
        self.company_name = company_name
        self.period_label = period_label

    def header(self) -> None:
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 6, self.company_name, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, f"Period: {self.period_label}", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str) -> None:
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def sub_heading(self, text: str) -> None:
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")

    def line_item(self, label: str, amount: str, bold: bool = False) -> None:
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 9)
        self.cell(140, 6, label)
        self.cell(0, 6, amount, align="R", new_x="LMARGIN", new_y="NEXT")

    def separator(self) -> None:
        y = self.get_y()
        self.line(10, y, 200, y)
        self.ln(2)


def build_management_accounts_pdf(
    *,
    company_name: str,
    period_label: str,
    pl_data: dict[str, Any],
    bs_data: dict[str, Any],
    cf_data: dict[str, Any],
) -> bytes:
    """Build a combined management accounts PDF.

    Returns the raw PDF bytes.
    """
    pdf = _MgmtAccountsPDF(company_name, period_label)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Cover page ────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 15, "Management Accounts", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 16)
    pdf.cell(0, 10, company_name, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, period_label, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    pdf.set_font("Helvetica", "I", 9)
    now = datetime.now(tz=UTC)
    pdf.cell(
        0,
        8,
        f"Prepared: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    # ── Profit & Loss ─────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("Profit & Loss Statement")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(
        0,
        5,
        f"{pl_data.get('from_date', '')} to {pl_data.get('to_date', '')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    pdf.sub_heading("Revenue")
    for line in pl_data.get("revenue_lines", []):
        pdf.line_item(f"  {line.get('code', '')} {line.get('name', '')}", line.get("balance", ""))
    pdf.separator()
    pdf.line_item("Total Revenue", pl_data.get("total_revenue", "0.00"), bold=True)
    pdf.ln(4)

    pdf.sub_heading("Expenses")
    for line in pl_data.get("expense_lines", []):
        pdf.line_item(f"  {line.get('code', '')} {line.get('name', '')}", line.get("balance", ""))
    pdf.separator()
    pdf.line_item("Total Expenses", pl_data.get("total_expenses", "0.00"), bold=True)
    pdf.ln(4)

    pdf.separator()
    pdf.line_item("Net Profit / (Loss)", pl_data.get("net_profit", "0.00"), bold=True)

    # ── Balance Sheet ─────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("Balance Sheet")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 5, f"As at {bs_data.get('as_of', '')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    for section_key, section_label in [
        ("assets", "Assets"),
        ("liabilities", "Liabilities"),
        ("equity", "Equity"),
    ]:
        section = bs_data.get(section_key, {})
        pdf.sub_heading(section_label)
        for line in section.get("lines", []):
            pdf.line_item(
                f"  {line.get('code', '')} {line.get('name', '')}",
                line.get("balance", ""),
            )
        pdf.separator()
        pdf.line_item(f"Total {section_label}", section.get("total", "0.00"), bold=True)
        pdf.ln(3)

    # ── Cash Flow Statement ───────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("Cash Flow Statement")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(
        0,
        5,
        f"{cf_data.get('from_date', '')} to {cf_data.get('to_date', '')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    pdf.sub_heading("Operating Activities")
    for line in cf_data.get("operating_activities", []):
        pdf.line_item(f"  {line.get('label', '')}", line.get("amount", ""))
    pdf.ln(2)

    pdf.sub_heading("Investing Activities")
    for line in cf_data.get("investing_activities", []):
        pdf.line_item(f"  {line.get('label', '')}", line.get("amount", ""))
    pdf.ln(2)

    pdf.sub_heading("Financing Activities")
    for line in cf_data.get("financing_activities", []):
        pdf.line_item(f"  {line.get('label', '')}", line.get("amount", ""))
    pdf.ln(2)

    pdf.separator()
    pdf.line_item("Net Change in Cash", cf_data.get("net_change", "0.00"), bold=True)
    pdf.line_item("Opening Cash", cf_data.get("opening_cash", "0.00"))
    pdf.line_item("Closing Cash", cf_data.get("closing_cash", "0.00"), bold=True)

    return bytes(pdf.output())
