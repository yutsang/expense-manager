"""PDF rendering adapters.

The rendering logic is kept out of the API layer so it can be called from
services (e.g. ``send_invoice`` attaches the rendered PDF to email) and
from workers (nightly statement PDFs).
"""

from __future__ import annotations

from app.infra.pdf.invoice_pdf import render_invoice_pdf

__all__ = ["render_invoice_pdf"]
