"""Event Intelligence Capability Contract v1."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

CAPABILITY_CONTRACT_VERSION = "1.0"
Version = Annotated[str, StringConstraints(pattern=r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")]


class MediaLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_bytes: int = Field(gt=0)
    allowed_content_types: tuple[Literal["image/jpeg", "image/png", "image/webp"], ...] = Field(
        min_length=1
    )

    @field_validator("allowed_content_types")
    @classmethod
    def content_types_must_be_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("allowed content types must be unique")
        return value


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    capability_contract_version: Literal["1.0"]
    platform_version: Version
    api_versions: tuple[Version, ...] = Field(min_length=1)
    canonical_schema_versions: tuple[Version, ...] = Field(min_length=1)
    processor_contract_versions: tuple[Literal["1.0"], ...] = Field(min_length=1)
    enrichment_result_versions: tuple[Literal["1.0"], ...] = Field(min_length=1)
    supported_subject_types: tuple[Literal["review_item"], ...] = Field(min_length=1)
    supported_evidence_types: tuple[Literal["snapshot"], ...] = Field(min_length=1)
    claim_writeback: bool
    model_invocation: bool
    replay: bool
    dry_run: bool
    media_limits: MediaLimits
