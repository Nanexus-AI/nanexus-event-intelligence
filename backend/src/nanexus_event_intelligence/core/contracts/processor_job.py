"""Processor Job Contract v1.

This module is deliberately independent of persistence models, Redis envelopes,
source adapters, and provider SDKs. The normative wire specification is
``docs/schemas/processor-job-v1.schema.json``.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

PROCESSOR_CONTRACT_VERSION = "1.0"
ContractVersion = Literal["1.0"]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Revision = Annotated[str, StringConstraints(min_length=1, max_length=255)]
IdempotencyKey = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class SubjectType(StrEnum):
    REVIEW_ITEM = "review_item"


class EvidenceType(StrEnum):
    SNAPSHOT = "snapshot"


class EvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    PENDING = "pending"
    EXPIRED = "expired"
    DENIED = "denied"
    UNKNOWN = "unknown"


class PrivacyRoute(StrEnum):
    LOCAL_ONLY = "local_only"
    CLOUD_REDACTED = "cloud_redacted"
    CLOUD_ALLOWED = "cloud_allowed"


class RequestedOutputType(StrEnum):
    CAPTION = "caption"
    TAGS = "tags"


class EvidenceRef(BaseModel):
    """Opaque Evidence reference; source URLs and credentials are forbidden."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: UUID
    media_type: EvidenceType
    privacy_class: PrivacyRoute
    availability: EvidenceAvailability
    purpose: Identifier


class RequestedOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    output_type: RequestedOutputType
    schema_version: Literal["1.0"]
    required: bool


class PrivacyPolicy(BaseModel):
    """Policy selected by the platform; enforcement belongs to the platform boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: Identifier
    policy_version: Revision
    route: PrivacyRoute
    external_network_allowed: bool
    retention: Literal["none", "ephemeral"]


class ProcessorJob(BaseModel):
    """Transport-neutral request for one idempotent enrichment attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: UUID
    contract_version: ContractVersion
    processor_type: Identifier
    subject_type: SubjectType
    subject_id: UUID
    subject_revision: Revision
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=16)
    requested_outputs: tuple[RequestedOutput, ...] = Field(min_length=1, max_length=16)
    privacy_policy: PrivacyPolicy
    idempotency_key: IdempotencyKey
    requested_at: datetime
    trace_id: UUID

    @field_validator("requested_at")
    @classmethod
    def requested_at_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("requested_at must include a timezone offset")
        return value

    @field_validator("requested_outputs")
    @classmethod
    def output_types_must_be_unique(
        cls, value: tuple[RequestedOutput, ...]
    ) -> tuple[RequestedOutput, ...]:
        kinds = [item.output_type for item in value]
        if len(kinds) != len(set(kinds)):
            raise ValueError("requested output types must be unique")
        return value

    @field_validator("privacy_policy")
    @classmethod
    def privacy_route_must_be_consistent(cls, value: PrivacyPolicy) -> PrivacyPolicy:
        if value.route is PrivacyRoute.LOCAL_ONLY and value.external_network_allowed:
            raise ValueError("local_only policy cannot allow external network access")
        return value
