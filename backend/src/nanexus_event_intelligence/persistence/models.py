from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid6 import uuid7


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> UUID:
    return uuid7()


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON}


class IdMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class SourceInstance(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "source_instances"
    __table_args__ = (
        UniqueConstraint("source_type", "name", name="uq_source_instances_type_name"),
        CheckConstraint(
            "health_status IN ('starting','healthy','degraded','offline','stopped')",
            name="ck_source_instances_health_status",
        ),
    )

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(128))
    adapter_version: Mapped[str] = mapped_column(String(128), nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    config_ref: Mapped[str | None] = mapped_column(String(512))
    trust_boundary: Mapped[str] = mapped_column(String(64), default="local", nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), default="starting", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Camera(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_cameras_site_name"),)

    site_id: Mapped[str] = mapped_column(String(255), default="default", nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    zones: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    privacy_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class SourceEntityMap(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "source_entity_maps"
    __table_args__ = (
        UniqueConstraint(
            "source_instance_id",
            "namespace",
            "source_entity_id",
            name="uq_source_entity_external_identity",
        ),
        Index("ix_source_entity_internal", "entity_type", "internal_entity_id"),
    )

    source_instance_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_instances.id", ondelete="CASCADE"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    internal_entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class RawSourceMessage(IdMixin, Base):
    __tablename__ = "raw_source_messages"
    __table_args__ = (
        UniqueConstraint("source_instance_id", "dedupe_key", name="uq_raw_source_dedupe"),
        Index("ix_raw_source_observed_at", "source_instance_id", "observed_at"),
    )

    source_instance_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_instances.id", ondelete="CASCADE"), nullable=False
    )
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(512), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quarantine_reason: Mapped[str | None] = mapped_column(Text)


class Observation(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("source_instance_id", "dedupe_key", name="uq_observations_dedupe"),
        CheckConstraint(
            "event_kind IN ('review','object','motion','audio','sensor','system','unknown')",
            name="ck_observations_event_kind",
        ),
        CheckConstraint(
            "lifecycle IN ('started','updated','ended','corrected','deleted')",
            name="ck_observations_lifecycle",
        ),
        Index("ix_observations_camera_occurred", "camera_id", "occurred_at"),
        Index(
            "ix_observations_source_entity",
            "source_instance_id",
            "source_namespace",
            "source_entity_id",
        ),
    )

    source_instance_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_instances.id", ondelete="RESTRICT"), nullable=False
    )
    camera_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cameras.id", ondelete="SET NULL")
    )
    raw_message_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("raw_source_messages.id", ondelete="SET NULL")
    )
    source_namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(512), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    partial_history: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    zones: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    extensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ReviewItem(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "review_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','ended','corrected','deleted')", name="ck_review_status"
        ),
        Index("ix_review_camera_start", "camera_id", "start_at"),
    )

    camera_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cameras.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    severity: Mapped[str | None] = mapped_column(String(32))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    labels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    zones: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class ReviewObservation(Base):
    __tablename__ = "review_observations"

    review_item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("review_items.id", ondelete="CASCADE"), primary_key=True
    )
    observation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("observations.id", ondelete="CASCADE"), primary_key=True
    )


class ObservedObject(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "observed_objects"
    __table_args__ = (
        UniqueConstraint("observation_id", "object_key", name="uq_observed_object_key"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_observed_object_confidence",
        ),
    )

    observation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("observations.id", ondelete="CASCADE"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    sub_labels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    stationary: Mapped[bool | None] = mapped_column(Boolean)
    track: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Evidence(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "privacy_class IN ('local_only','cloud_redacted','cloud_allowed')",
            name="ck_evidence_privacy_class",
        ),
        CheckConstraint(
            "availability IN ('available','pending','expired','denied','unknown')",
            name="ck_evidence_availability",
        ),
        UniqueConstraint("source_instance_id", "source_ref", name="uq_evidence_source_ref"),
    )

    source_instance_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_instances.id", ondelete="RESTRICT"), nullable=False
    )
    observation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("observations.id", ondelete="SET NULL")
    )
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_class: Mapped[str] = mapped_column(String(32), default="local_only", nullable=False)
    availability: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ModelInvocationEvidence(Base):
    __tablename__ = "model_invocation_evidence"

    model_invocation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("model_invocations.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True
    )


class ContextSnapshot(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "context_snapshots"
    __table_args__ = (Index("ix_context_subject_captured", "subject_type", "captured_at"),)

    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID | None] = mapped_column(Uuid)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ModelInvocation(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "model_invocations"

    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    runtime_version: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    privacy_route: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_units: Mapped[int | None] = mapped_column(Integer)
    output_units: Mapped[int | None] = mapped_column(Integer)
    cost_micros: Mapped[int | None] = mapped_column(Integer)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(128))


class Claim(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_claim_confidence",
        ),
    )

    observation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("observations.id", ondelete="SET NULL")
    )
    model_invocation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("model_invocations.id", ondelete="SET NULL")
    )
    producer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    producer_version: Mapped[str] = mapped_column(String(128), nullable=False)
    predicate: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence_unavailable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    claim_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("claims.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True
    )


class Decision(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("subject_id", "revision", name="uq_decision_subject_revision"),
        CheckConstraint(
            "outcome IN ('send','suppress','enrich','escalate','hold','no_action')",
            name="ck_decision_outcome",
        ),
        CheckConstraint("revision >= 1", name="ck_decision_revision_positive"),
    )

    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    context_snapshot_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("context_snapshots.id", ondelete="SET NULL")
    )
    supersedes_decision_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("decisions.id", ondelete="SET NULL")
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    rule_trace: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_unavailable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    degraded_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class DecisionClaim(Base):
    __tablename__ = "decision_claims"

    decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decisions.id", ondelete="CASCADE"), primary_key=True
    )
    claim_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("claims.id", ondelete="RESTRICT"), primary_key=True
    )


class DecisionEvidence(Base):
    __tablename__ = "decision_evidence"

    decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decisions.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True
    )


class Action(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "actions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_actions_idempotency_key"),
        CheckConstraint(
            "status IN ('planned','running','succeeded','retryable_failure','permanent_failure')",
            name="ck_actions_status",
        ),
    )

    decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decisions.id", ondelete="RESTRICT"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class Notification(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("channel", "idempotency_key", name="uq_notification_channel_key"),
        CheckConstraint(
            "stage IN ('initial','enhanced','resolved','escalated')",
            name="ck_notification_stage",
        ),
    )

    action_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("actions.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(512))
    delivery_status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)


class Feedback(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('important','not_important','false_positive','uncertain')",
            name="ck_feedback_verdict",
        ),
    )

    decision_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("decisions.id", ondelete="RESTRICT"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    supersedes_feedback_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("feedback.id", ondelete="SET NULL")
    )


class AuditRecord(IdMixin, Base):
    __tablename__ = "audit_records"
    __table_args__ = (Index("ix_audit_target_time", "target_type", "target_id", "occurred_at"),)

    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(Uuid)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class OutboxEvent(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_outbox_dedupe_key"),
        Index("ix_outbox_unpublished", "published_at", "created_at"),
    )

    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class IngestCheckpoint(IdMixin, Base):
    __tablename__ = "ingest_checkpoints"
    __table_args__ = (
        UniqueConstraint("source_instance_id", "stream", name="uq_ingest_checkpoint_stream"),
    )

    source_instance_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("source_instances.id", ondelete="CASCADE"), nullable=False
    )
    stream: Mapped[str] = mapped_column(String(512), nullable=False)
    cursor: Mapped[str] = mapped_column(String(1024), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
