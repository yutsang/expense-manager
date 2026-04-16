"""Simple email sender using Resend API (falls back to log-only if not configured)."""
from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    from_addr: str | None = None,
) -> bool:
    """Send an email via Resend API. Returns True on success, False on failure."""
    settings = get_settings()
    api_key = getattr(settings, "resend_api_key", None) or ""
    from_addr = from_addr or getattr(settings, "email_from", "noreply@aegis-erp.com")

    if not api_key:
        log.info("email.skipped_no_api_key", to=to, subject=subject)
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": from_addr, "to": [to], "subject": subject, "html": html},
            )
            resp.raise_for_status()
            log.info("email.sent", to=to, subject=subject)
            return True
    except Exception as exc:
        log.error("email.send_failed", to=to, error=str(exc))
        return False
