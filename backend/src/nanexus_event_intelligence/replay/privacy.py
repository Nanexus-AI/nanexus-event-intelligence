"""Best-effort credential removal for portable replay exports."""

from typing import Any
from urllib.parse import urlsplit, urlunsplit

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "proxy_secret",
    "secret",
    "token",
}
REDACTED = "[REDACTED]"


def sanitize_export(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): REDACTED if str(key).lower() in SENSITIVE_KEYS else sanitize_export(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_export(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_export(item) for item in value]
    if isinstance(value, str):
        return _sanitize_url(value)
    return value


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.scheme not in {"http", "https", "mqtt", "mqtts", "rtsp", "rtsps"}:
        return value
    if parsed.username is None and parsed.password is None:
        return value
    if parsed.hostname is None:
        return REDACTED
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    try:
        parsed_port = parsed.port
    except ValueError:
        return REDACTED
    port = f":{parsed_port}" if parsed_port else ""
    return urlunsplit(
        (parsed.scheme, f"{REDACTED}@{host}{port}", parsed.path, parsed.query, parsed.fragment)
    )
