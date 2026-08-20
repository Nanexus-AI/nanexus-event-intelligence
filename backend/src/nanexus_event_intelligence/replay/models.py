"""Versioned models for portable canonical replay bundles."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReplayEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: UUID
    source_instance_id: UUID
    source_namespace: str
    source_entity_id: str
    source_revision: str
    dedupe_key: str
    schema_version: str
    event_kind: str
    lifecycle: str
    occurred_at: datetime
    observed_at: datetime
    start_at: datetime | None = None
    end_at: datetime | None = None
    partial_history: bool = False
    labels: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at", "observed_at", "start_at", "end_at")
    @classmethod
    def normalize_event_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("replay event datetimes must include a timezone")
        return value.astimezone(UTC)


class ReplayRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int = Field(ge=0)
    event_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    event: ReplayEvent


class ReplayManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["nanexus-replay-bundle/1.0"] = "nanexus-replay-bundle/1.0"
    bundle_id: UUID
    source_instance_id: UUID
    source_type: str
    source_version: str | None = None
    exported_at: datetime
    event_count: int = Field(ge=0)
    first_occurred_at: datetime | None = None
    last_occurred_at: datetime | None = None
    events_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    contains_credentials: Literal[False] = False
    privacy_review_required: Literal[True] = True
    production_side_effects_enabled: Literal[False] = False
    truncated: bool = False

    @field_validator("exported_at", "first_occurred_at", "last_occurred_at")
    @classmethod
    def normalize_manifest_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("replay manifest datetimes must include a timezone")
        return value.astimezone(UTC)


class ReplayEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    bundle_id: UUID
    sequence: int = Field(ge=0)
    replayed_at: datetime
    event: ReplayEvent

    @field_validator("replayed_at")
    @classmethod
    def normalize_replayed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("replayed_at must include a timezone")
        return value.astimezone(UTC)
