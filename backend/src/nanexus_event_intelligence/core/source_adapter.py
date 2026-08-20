"""Vendor-neutral source adapter contract used by the core."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CapabilitySet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    live_events: bool
    historical_query: bool
    media_fetch: bool
    object_tracks: bool
    review_groups: bool
    semantic_metadata: bool
    health: bool
    writeback: bool


class SourceDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0"
    source_type: str
    source_version: str | None = None
    adapter_version: str
    capabilities: CapabilitySet


class HealthStatus(StrEnum):
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    STOPPED = "stopped"


class SourceHealth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: HealthStatus
    last_received_at: datetime | None = None
    ingest_lag_seconds: float | None = Field(default=None, ge=0)
    reconnect_count: int = Field(default=0, ge=0)
    source_version: str | None = None
    adapter_version: str
    recent_error: str | None = None


class CanonicalSourceEvent(BaseModel):
    """Stable event envelope. Vendor payloads must not appear in this model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "1.0"
    event_id: UUID
    source_instance_id: UUID
    source_namespace: str
    source_entity_id: str
    source_revision: str
    dedupe_key: str
    event_kind: Literal["review", "object", "motion", "audio", "sensor", "system", "unknown"]
    lifecycle: Literal["started", "updated", "ended", "corrected", "deleted"]
    occurred_at: datetime
    observed_at: datetime
    camera_id: UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    partial_history: bool
    labels: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    objects: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)
    raw_ref: str | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)


CanonicalEventSink = Callable[[CanonicalSourceEvent], Awaitable[None]]


class AdapterHandle(Protocol):
    async def stop(self) -> None: ...


class SourceAdapter(Protocol):
    def describe(self) -> SourceDescriptor: ...

    def validate(self, config: dict[str, Any]) -> ValidationReport: ...

    async def start(self, emit: CanonicalEventSink) -> AdapterHandle: ...

    def health(self) -> SourceHealth: ...

    async def stop(self) -> None: ...
