"""Parse form-encoded and JSON request bodies."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl

from stario import HttpException, datastar as ds
from stario.http.context import Context

# Request bodies stay small: the biggest legit payload (the profile form) is
# a few KB. Cap well under Stario's 10 MB transport limit so a multi-MB body
# is refused before a byte is parsed — an uncapped parse_qsl on megabytes of
# "a=1&" stalls the event loop for seconds per request.
MAX_BODY_BYTES = 64 * 1024
MAX_FORM_FIELDS = 100


async def read_body(c: Context) -> bytes:
    """The request body, or a 413 when it exceeds the 64 KB input cap.

    The declared length is checked first so a huge upload is refused without
    buffering it; the real size is re-checked after the read for chunked or
    lying clients.
    """
    declared = c.req.headers.get("content-length")
    if declared is not None:
        try:
            declared_len = int(declared)
        except ValueError:
            declared_len = -1
        if declared_len > MAX_BODY_BYTES:
            raise HttpException(413, "Request body too large")
    body = await c.req.body()
    if len(body) > MAX_BODY_BYTES:
        raise HttpException(413, "Request body too large")
    return body


def clean_field(value: object) -> str | None:
    """Return a usable text field, or None when it must count as missing.

    A field only counts when it is a ``str`` that survives ``.encode("utf-8")``
    (a lone surrogate smuggled in through a JSON ``\\ud800`` escape crashes
    redis, hmac and asyncpg downstream) and carries no NUL byte (Postgres
    refuses them). Anything else is treated as absent so the handler's normal
    required-field 400 path fires instead of a 500.
    """
    if not isinstance(value, str) or "\x00" in value:
        return None
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return value


def _clean_mapping(mapping: dict) -> dict[str, str]:
    """Keep only the fields whose key and value both survive clean_field."""
    out: dict[str, str] = {}
    for key, value in mapping.items():
        k, v = clean_field(key), clean_field(value)
        if k is not None and v is not None:
            out[k] = v
    return out


def _clean_signal_value(value: Any) -> Any:
    """Strip unusable strings out of a (possibly nested) signals payload."""
    if isinstance(value, str):
        return clean_field(value)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = clean_field(k)
            if key is not None:
                out[key] = _clean_signal_value(v)
        return out
    if isinstance(value, list):
        return [_clean_signal_value(v) for v in value]
    return value


async def parse_form(c: Context) -> dict[str, str]:
    """Flat form/signal fields; hostile bodies decode as empty input."""
    body = await read_body(c)
    if not body:
        return {}
    content_type = c.req.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = json.loads(body)
        except (ValueError, RecursionError, TypeError):
            # ValueError covers JSONDecodeError and the UnicodeDecodeError
            # raised on invalid UTF-8 bytes; RecursionError on deeply nested
            # arrays. All mean "no usable input", not a 500.
            return {}
        if not isinstance(data, dict):
            return {}
        return _clean_mapping(data)
    try:
        # max_num_fields stops a "a=1&" flood inside the cap from expanding
        # into tens of thousands of pairs; over the limit it raises ValueError
        # and the body counts as empty, same as any malformed input.
        return _clean_mapping(
            dict(parse_qsl(body.decode("utf-8"), max_num_fields=MAX_FORM_FIELDS))
        )
    except (ValueError, RecursionError, TypeError):
        return {}


async def safe_signals(c: Context) -> dict[str, Any]:
    """Datastar signals as a dict; malformed JSON/non-dict bodies become {}."""
    # Prime the cached body under the size cap: for methods where signals
    # travel in the body, read_signals reuses these same bytes.
    await read_body(c)
    try:
        signals = await ds.read_signals(c.req)
    except (ValueError, RecursionError, TypeError):
        return {}
    cleaned = _clean_signal_value(signals)
    return cleaned if isinstance(cleaned, dict) else {}


def str_field(mapping: dict, *keys: str) -> str:
    """Return the first non-empty str value among keys; non-str counts as missing."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
