from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from nanexus_event_intelligence.notifications.models import (
    DeliveryError,
    DeliveryResult,
    NotificationMessage,
)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class WebhookNotificationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str
    trusted_internal: bool = False
    secret: SecretStr | None = None
    timeout_seconds: float = Field(default=5, gt=0, le=30)

    @model_validator(mode="after")
    def validate_security_boundary(self) -> "WebhookNotificationConfig":
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("url cannot contain credentials, query, or fragment")
        if parsed.scheme == "http" and not self.trusted_internal:
            raise ValueError("plain HTTP requires trusted_internal=true")
        return self


class WebhookNotificationAdapter:
    def __init__(
        self,
        config: WebhookNotificationConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout_seconds), follow_redirects=False
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def deliver(self, message: NotificationMessage) -> DeliveryResult:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": message.idempotency_key,
        }
        if self.config.secret is not None:
            headers["X-Nanexus-Webhook-Secret"] = self.config.secret.get_secret_value()
        try:
            response = await self._client.post(
                self.config.url,
                content=message.model_dump_json(),
                headers=headers,
                follow_redirects=False,
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            raise DeliveryError("webhook request failed", retryable=True) from None
        if 200 <= response.status_code < 300:
            external_id = response.headers.get("x-request-id")
            return DeliveryResult(external_message_id=external_id[:512] if external_id else None)
        if response.status_code in RETRYABLE_STATUS:
            raise DeliveryError("webhook is temporarily unavailable", retryable=True)
        if 300 <= response.status_code < 400:
            raise DeliveryError("webhook redirect was refused", retryable=False)
        raise DeliveryError("webhook rejected the notification", retryable=False)
