from sqlalchemy import CheckConstraint, UniqueConstraint

from nanexus_event_intelligence.persistence.models import (
    Claim,
    ModelInvocation,
    ProcessorJob,
    ReviewItem,
)


def test_processor_job_fields_and_constraints() -> None:
    columns = ProcessorJob.__table__.columns
    assert {
        "id",
        "processor_type",
        "subject_type",
        "subject_id",
        "subject_revision",
        "contract_version",
        "idempotency_key",
        "trace_id",
        "status",
        "payload",
        "attempt_count",
        "available_at",
        "started_at",
        "completed_at",
        "last_error_code",
        "last_error",
        "created_at",
        "updated_at",
    } == set(columns.keys())
    constraints = ProcessorJob.__table__.constraints
    assert any(
        isinstance(item, UniqueConstraint) and item.name == "uq_processor_jobs_idempotency_key"
        for item in constraints
    )
    assert any(
        isinstance(item, CheckConstraint) and item.name == "ck_processor_jobs_status"
        for item in constraints
    )
    assert {item.name for item in ProcessorJob.__table__.indexes} == {
        "ix_processor_jobs_status_available"
    }


def test_extended_public_persistence_fields() -> None:
    assert "source_revision" in ReviewItem.__table__.columns
    assert "review_item_id" in Claim.__table__.columns
    assert {
        "processor_job_id",
        "status",
        "started_at",
        "completed_at",
        "error_message",
        "external_network_used",
    } <= set(ModelInvocation.__table__.columns.keys())
    assert any(
        isinstance(item, UniqueConstraint) and item.name == "uq_model_invocation_processor_job"
        for item in ModelInvocation.__table__.constraints
    )
