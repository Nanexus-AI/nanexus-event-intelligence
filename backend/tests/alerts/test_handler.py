from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.alerts.handler import ShadowDecisionHandler
from nanexus_event_intelligence.persistence.models import (
    Base,
    Decision,
    Observation,
    ObservedObject,
    OutboxEvent,
    SourceInstance,
)
from nanexus_event_intelligence.pipeline.worker import StreamEnvelope


async def test_shadow_handler_persists_idempotent_decision_after_feedback_anchor() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_id, observation_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    async with factory.begin() as session:
        session.add(
            SourceInstance(
                id=source_id,
                source_type="test",
                name="source",
                adapter_version="1",
                capabilities={},
            )
        )
        session.add(
            Observation(
                id=observation_id,
                source_instance_id=source_id,
                source_namespace="object",
                source_entity_id="person-1",
                source_revision="1",
                dedupe_key="person-1:new",
                schema_version="1.0",
                event_kind="object",
                lifecycle="started",
                occurred_at=now,
                observed_at=now,
                labels=["person"],
                zones=["porch"],
            )
        )
        session.add(
            Decision(
                subject_type="observation",
                subject_id=observation_id,
                revision=1,
                outcome="no_action",
                policy_id="ui-feedback-anchor",
                policy_version="1.0.0",
                reasons=["anchor"],
            )
        )
        session.add(
            ObservedObject(
                observation_id=observation_id,
                object_key="person-1",
                label="person",
                stationary=True,
            )
        )
    envelope = StreamEnvelope(
        outbox_id=str(uuid4()),
        dedupe_key="canonical:person-1:new",
        aggregate_type="object",
        aggregate_id=str(uuid4()),
        event_type="canonical.observation.persisted",
        schema_version="1.0",
        payload={"event": {"source_instance_id": str(source_id), "dedupe_key": "person-1:new"}},
    )
    handler = ShadowDecisionHandler(factory)
    await handler(envelope)
    await handler(envelope)

    async with factory() as session:
        decisions = list(
            (await session.scalars(select(Decision).order_by(Decision.revision))).all()
        )
        assert len(decisions) == 2
        assert decisions[1].revision == 2
        assert decisions[1].outcome == "escalate"
        assert decisions[1].rule_trace["matched_rule_id"] == "person.priority-zone"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "shadow.decision.created")
            )
            == 1
        )
    await engine.dispose()


async def test_shadow_handler_ignores_its_own_outbox_event() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine)
    handler = ShadowDecisionHandler(factory)
    envelope = StreamEnvelope(
        outbox_id=str(uuid4()),
        dedupe_key="shadow:x",
        aggregate_type="decision",
        aggregate_id=str(uuid4()),
        event_type="shadow.decision.created",
        schema_version="1.0",
        payload={},
    )
    await handler(envelope)
    await engine.dispose()
