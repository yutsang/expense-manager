"""Email sender using the Resend API (falls back to log-only if not configured)."""

from __future__ import annotations

import base64
from typing import TypedDict

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class EmailAttachment(TypedDict):
    """An email attachment spec.

    ``content`` is the raw bytes of the file; this module handles the base64
    encoding required by the Resend API.
    """

    filename: str
    content: bytes


async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    from_addr: str | None = None,
    attachments: list[EmailAttachment] | None = None,
) -> bool:
    """Send an email via Resend API. Returns True on success, False on failure."""
    settings = get_settings()
    api_key = getattr(settings, "resend_api_key", None) or ""
    from_addr = from_addr or getattr(settings, "email_from", "noreply@aegis-erp.com")

    if not api_key:
        log.info(
            "email.skipped_no_api_key",
            to=to,
            subject=subject,
            attachments=len(attachments or []),
        )
        return False

    payload: dict = {
        "from": from_addr,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if attachments:
        payload["attachments"] = [
            {
                "filename": a["filename"],
                "content": base64.b64encode(a["content"]).decode("ascii"),
            }
            for a in attachments
        ]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            log.info("email.sent", to=to, subject=subject, attachments=len(attachments or []))
            return True
    except Exception as exc:
        log.error("email.send_failed", to=to, error=str(exc))
        return False
