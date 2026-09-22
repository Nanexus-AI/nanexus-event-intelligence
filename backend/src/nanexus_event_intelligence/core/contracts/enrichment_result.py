"""Enrichment Result Contract v1, independent of persistence and transport."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

RESULT_CONTRACT_VERSION = "1.0"
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=255)]


class ResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    ABSTAINED = "abstained"
    FAILED = "failed"


class PrivacyRoute(StrEnum):
    LOCAL_ONLY = "local_only"
    CLOUD_REDACTED = "cloud_redacted"
    CLOUD_ALLOWED = "cloud_allowed"


class ModelInvocationFacts(BaseModel):
    """Processor facts; the platform creates the authoritative record."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    invocation_id: UUID
    provider: Identifier
    model: Identifier
    model_version: Identifier
    outcome: ResultStatus
    started_at: datetime
    completed_at: datetime
    privacy_route: PrivacyRoute
    external_network_used: bool

    @field_validator("started_at", "completed_at")
    @classmethod
    def timestamps_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("invocation timestamps must include a timezone offset")
        return value

    @model_validator(mode="after")
    def invocation_is_consistent(self) -> "ModelInvocationFacts":
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.privacy_route is PrivacyRoute.LOCAL_ONLY and self.external_network_used:
            raise ValueError("local_only invocation cannot use an external network")
        return self


class CaptionClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    claim_type: Literal["caption"]
    schema_version: Literal["1.0"]
    text: ShortText
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: tuple[UUID, ...] = Field(min_length=1, max_length=16)


class TagsClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    claim_type: Literal["tags"]
    schema_version: Literal["1.0"]
    tags: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: tuple[UUID, ...] = Field(min_length=1, max_length=16)

    @field_validator("tags")
    @classmethod
    def tags_must_be_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("tags must be unique")
        return value


Claim = Annotated[CaptionClaim | TagsClaim, Field(discriminator="claim_type")]


class ResultError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: Identifier
    reason: ShortText
    retryable: bool


class EnrichmentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    job_id: UUID
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    contract_version: Literal["1.0"]
    status: ResultStatus
    model_invocation: ModelInvocationFacts
    claims: tuple[Claim, ...] = Field(max_length=16)
    errors: tuple[ResultError, ...] = Field(max_length=16)
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def completed_at_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must include a timezone offset")
        return value

    @model_validator(mode="after")
    def status_payload_must_be_consistent(self) -> "EnrichmentResult":
        if self.model_invocation.outcome is not self.status:
            raise ValueError("model invocation outcome must match result status")
        if self.completed_at < self.model_invocation.completed_at:
            raise ValueError("result cannot complete before its invocation")
        if self.status is ResultStatus.SUCCEEDED and (not self.claims or self.errors):
            raise ValueError("succeeded result requires claims and forbids errors")
        if self.status is ResultStatus.ABSTAINED and (self.claims or not self.errors):
            raise ValueError("abstained result forbids claims and requires a reason")
        if self.status is ResultStatus.FAILED and (self.claims or not self.errors):
            raise ValueError("failed result forbids claims and requires errors")
        return self
