"""Deterministic secret removal for recorded Frigate payloads."""

import re
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "username",
    "user",
}
URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/@\s]+@")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): REDACTED if str(key).lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return URL_CREDENTIALS.sub(r"\g<scheme>[REDACTED]@", value)
    return value
