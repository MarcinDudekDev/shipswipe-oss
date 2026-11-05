"""Email address validation and rate-limiter key normalisation."""

from __future__ import annotations

_FORBIDDEN = set(' \t\n\r\f\v,;<>"\'')


def normalize_email(raw: object) -> str | None:
    """Return the canonical address, or None for anything but one clean address.

    Strictly single-address: a well-formed local@domain with a dotted domain,
    no display-name, list, or injection characters. Anything else would let one
    request fan mail out to many recipients or key the limiter on a variant.
    """
    if not isinstance(raw, str):
        return None
    email = raw.strip().lower()
    if not email or len(email) > 320 or email.count("@") != 1:
        return None
    local, domain = email.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        return None
    if any(ch in _FORBIDDEN or ord(ch) < 32 or ord(ch) == 127 for ch in email):
        return None
    return email


def limiter_key(email: str) -> str:
    """Rate-limit key: the address minus any +tag so tags/case can't dodge the bucket.

    Gmail aliases collapse too: gmail.com and googlemail.com are one mailbox,
    and Gmail ignores dots in the local part.
    """
    local, _, domain = email.partition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"
