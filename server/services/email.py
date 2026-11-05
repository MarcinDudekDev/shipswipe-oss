"""Email delivery — captured in OUTBOX during tests/dev, sent over SMTP in prod."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from config import settings

log = logging.getLogger("shipswipe.email")

OUTBOX: list[dict[str, str]] = []


def _capture_active() -> bool:
    """True when mail is diverted to the in-memory OUTBOX instead of SMTP."""
    return settings.is_test or settings.app_env == "development"


def _capture(msg: dict[str, str]) -> None:
    """Stash the message in OUTBOX; in dev, print the link for passwordless login."""
    OUTBOX.append(msg)
    if settings.app_env == "development":
        # The README quickstart has no mailbox — the sign-in link must reach
        # stdout or a contributor can never log in. Development only.
        print(f"[dev mail] to={msg['to']} link={msg['link']}", flush=True)


def _send_smtp(*, to: str, subject: str, body: str) -> None:
    """Deliver one message over SMTP with STARTTLS + auth (production)."""
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    # smtplib.SMTP referenced via the module so it stays patchable in tests.
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


def send(*, to: str, subject: str, body: str, link: str) -> None:
    """Send an email. Test/dev capture to OUTBOX; production sends over SMTP."""
    msg = {"to": to, "subject": subject, "body": body, "link": link}
    if _capture_active():
        _capture(msg)
        return
    _send_smtp(to=to, subject=subject, body=body)


async def send_async(*, to: str, subject: str, body: str, link: str) -> None:
    """Non-blocking send: SMTP runs off the event loop; failures are logged
    and swallowed so a mail outage can't take request handling down with it."""
    msg = {"to": to, "subject": subject, "body": body, "link": link}
    if _capture_active():
        _capture(msg)
        return
    try:
        await asyncio.to_thread(_send_smtp, to=to, subject=subject, body=body)
    except Exception as exc:
        # Domain only — the full recipient address is PII in the logs, and so
        # is the exception text (SMTPRecipientsRefused echoes every refused
        # address): log the exception class and SMTP status code, no exc_info.
        code = getattr(exc, "smtp_code", None)
        log.warning(
            "SMTP send to *@%s failed: %s%s",
            to.rpartition("@")[2] or "?",
            type(exc).__name__,
            f" smtp_code={code}" if code is not None else "",
        )
