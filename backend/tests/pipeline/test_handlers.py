from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.persistence.models import Base, Observation, SourceInstance
from nanexus_event_intelligence.pipeline.handlers import ObservationProcessedHandler
from nanexus_event_intelligence.pipeline.worker import StreamEnvelope


@pytest.mark.asyncio
async def test_observation_handler_is_idempotent_and_commits_before_ack() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_id = uuid4()
    observation_id = uuid4()
    dedupe_key = "source:test:object:1"
    now = datetime.now(UTC)
    async with factory.begin() as session:
        session.add(
            SourceInstance(
                id=source_id,
                source_type="test",
                name="handler-test",
                adapter_version="1.0",
                capabilities={},
            )
        )
        session.add(
            Observation(
                id=observation_id,
                source_instance_id=source_id,
                source_namespace="object",
                source_entity_id="1",
                source_revision="1",
                dedupe_key=dedupe_key,
                schema_version="1.0",
                event_kind="object",
                lifecycle="started",
                occurred_at=now,
                observed_at=now,
            )
        )
    envelope = StreamEnvelope(
        outbox_id=str(uuid4()),
        dedupe_key=f"canonical:{dedupe_key}",
        aggregate_type="object",
        aggregate_id=str(uuid4()),
        event_type="canonical.observation.persisted",
        schema_version="1.0",
        payload={"event": {"source_instance_id": str(source_id), "dedupe_key": dedupe_key}},
    )
    handler = ObservationProcessedHandler(factory)

    await handler(envelope)
    await handler(envelope)

    async with factory() as session:
        observation = await session.get(Observation, observation_id)
        assert observation is not None
        assert observation.processed_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_observation_handler_ignores_other_domain_events() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine)
    handler = ObservationProcessedHandler(factory)
    envelope = StreamEnvelope(
        outbox_id=str(uuid4()),
        dedupe_key="shadow:test",
        aggregate_type="decision",
        aggregate_id=str(uuid4()),
        event_type="shadow.decision.created",
        schema_version="1.0",
        payload={},
    )
    await handler(envelope)
    await engine.dispose()
