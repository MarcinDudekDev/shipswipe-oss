"""Checkpoint 14 — real SMTP delivery in production [2026-06-25].

In test/dev the magic-link email is captured in the in-memory OUTBOX (no network).
In production (`APP_ENV=production`) it must actually be sent over SMTP with STARTTLS
and authentication. The suite never touches the network: smtplib.SMTP is monkeypatched
and we assert the email service drove it (STARTTLS + login + a send carrying the
recipient and the verify link).

Expected behavior:
  - `config.Settings` exposes `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`,
    `smtp_from` (read from env, with safe local defaults).
  - `services.email.send(...)` keeps OUTBOX capture for test/dev, and in production
    opens a connection via `smtplib.SMTP(host, port)` (module attribute, so it is
    patchable), calls `starttls()`, `login(user, password)`, and sends the message.
"""

import smtplib
import types


class _FakeSMTP:
    instances: list = []

    def __init__(self, host=None, port=0, *a, **k):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.sent: list = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self, *a, **k):
        pass

    def starttls(self, *a, **k):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg, *a, **k):
        self.sent.append(msg.as_string() if hasattr(msg, "as_string") else str(msg))

    def sendmail(self, from_addr, to_addrs, msg, *a, **k):
        self.sent.append(f"{to_addrs} {msg}")

    def quit(self):
        pass


def _prod_settings():
    return types.SimpleNamespace(
        app_env="production",
        is_test=False,
        base_url="https://shipswipe.example.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="shipswipe@example.com",
        smtp_password="secret-pass",
        smtp_from="shipswipe@example.com",
    )


def test_config_exposes_smtp_settings():
    from config import settings

    for attr in ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from"):
        assert hasattr(settings, attr), f"config must expose {attr} for production SMTP"


def test_test_mode_still_captures_to_outbox():
    import services.email as email

    email.OUTBOX.clear()
    email.send(
        to="t@example.com", subject="hi", body="link http://x/auth/verify?token=z",
        link="http://x/auth/verify?token=z",
    )
    assert email.OUTBOX, "test/dev mode must still capture emails to OUTBOX"
    assert email.OUTBOX[-1]["to"] == "t@example.com"


def test_production_send_uses_smtp(monkeypatch):
    import services.email as email

    _FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(email, "settings", _prod_settings())

    link = "https://shipswipe.example.com/auth/verify?token=abc123"
    email.send(
        to="visitor@example.com",
        subject="Your ShipSwipe login link",
        body=f"Click to sign in: {link}",
        link=link,
    )

    assert _FakeSMTP.instances, "production send() must open an SMTP connection"
    smtp = _FakeSMTP.instances[-1]
    assert smtp.started_tls, "production send() must use STARTTLS"
    assert smtp.logged_in == ("shipswipe@example.com", "secret-pass"), \
        "production send() must authenticate with the configured SMTP credentials"
    blob = "".join(smtp.sent)
    assert "visitor@example.com" in blob, "the sent message must carry the recipient"
    assert "abc123" in blob, "the sent message must carry the magic-link token"
