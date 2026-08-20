from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.persistence.models import (
    Base,
    Decision,
    SourceEntityMap,
    SourceInstance,
    new_id,
)
from nanexus_event_intelligence.persistence.repositories import SourceInstanceRepository

EXPECTED_TABLES = {
    "actions",
    "audit_records",
    "cameras",
    "claim_evidence",
    "claims",
    "context_snapshots",
    "decisions",
    "decision_claims",
    "decision_evidence",
    "evidence",
    "feedback",
    "ingest_checkpoints",
    "model_invocations",
    "model_invocation_evidence",
    "notifications",
    "observations",
    "observed_objects",
    "outbox_events",
    "raw_source_messages",
    "review_items",
    "review_observations",
    "source_entity_maps",
    "source_instances",
}


def test_metadata_contains_data_001_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


async def test_ids_are_uuid7(session: AsyncSession) -> None:
    source = await SourceInstanceRepository(session).add(
        SourceInstance(
            source_type="frigate",
            name="pilot",
            adapter_version="0.1.0",
            capabilities={"live_events": True},
        )
    )
    assert source.id.version == 7


async def test_external_identity_is_unique(session: AsyncSession) -> None:
    source = await SourceInstanceRepository(session).add(
        SourceInstance(
            source_type="frigate",
            name="pilot",
            adapter_version="0.1.0",
            capabilities={},
        )
    )
    values = {
        "source_instance_id": source.id,
        "namespace": "review",
        "source_entity_id": "external-1",
        "entity_type": "review_item",
        "internal_entity_id": new_id(),
    }
    session.add(SourceEntityMap(**values))
    await session.flush()
    session.add(SourceEntityMap(**values))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_decision_outcome_constraint(session: AsyncSession) -> None:
    decision = Decision(
        subject_type="review_item",
        subject_id=new_id(),
        revision=1,
        outcome="invalid",
        policy_id="test",
        policy_version="1",
        reasons=["test"],
    )
    session.add(decision)
    with pytest.raises(IntegrityError):
        await session.flush()


def test_utc_time_is_timezone_aware() -> None:
    now = datetime.now(UTC)
    assert now.utcoffset() is not None
