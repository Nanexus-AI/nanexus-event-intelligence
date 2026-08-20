from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    idempotency_key: str = Field(min_length=1, max_length=512)
    decision_id: UUID
    observation_id: UUID
    outcome: Literal["send", "escalate"]
    stage: Literal["initial", "escalated"]
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=1000)
    source: dict[str, Any]


class DeliveryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    external_message_id: str | None = Field(default=None, max_length=512)


class NotificationAdapter(Protocol):
    async def deliver(self, message: NotificationMessage) -> DeliveryResult: ...


class DeliveryError(RuntimeError):
    """Sanitized delivery error safe to persist and log."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable
