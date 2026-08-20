"""Security-sensitive Frigate HTTP client configuration."""

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class FrigateHttpConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str
    bearer_token: SecretStr | None = None
    username: str | None = None
    password: SecretStr | None = None
    proxy_secret: SecretStr | None = None
    trusted_internal: bool = False
    ca_bundle: Path | None = None
    timeout_seconds: float = Field(default=10, gt=0, le=120)
    max_retries: int = Field(default=3, ge=0, le=8)
    max_json_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    max_media_bytes: int = Field(default=25 * 1024 * 1024, ge=1024, le=200 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_security_boundary(self) -> "FrigateHttpConfig":
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an absolute HTTP(S) origin")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url cannot contain credentials, query, or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("base_url must not contain an application path")
        auth_modes = sum(
            [
                self.bearer_token is not None,
                self.proxy_secret is not None,
                self.username is not None or self.password is not None,
            ]
        )
        if auth_modes > 1:
            raise ValueError("configure exactly one HTTP authentication mode")
        if (self.username is None) != (self.password is None):
            raise ValueError("username and password must be configured together")
        if parsed.scheme == "http" and not self.trusted_internal:
            raise ValueError("plain HTTP requires trusted_internal=true")
        if parsed.port == 5000 and not self.trusted_internal:
            raise ValueError("Frigate port 5000 is restricted to trusted internal networks")
        return self

    @property
    def origin(self) -> str:
        return self.base_url.rstrip("/")
