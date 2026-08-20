import os
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from nanexus_event_intelligence.adapters.frigate.pipeline import FrigateIngestPipeline
from nanexus_event_intelligence.adapters.frigate.replay import load_fixture_bundle
from nanexus_event_intelligence.persistence.models import Observation, OutboxEvent, SourceInstance
from nanexus_event_intelligence.persistence.repositories import SourceInstanceRepository

BUNDLE = Path(__file__).parents[3] / "fixtures" / "frigate" / "0.17" / "vehicle-lifecycle"


@pytest.mark.asyncio
async def test_pipeline_transaction_on_postgresql() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            source = await SourceInstanceRepository(session).add(
                SourceInstance(
                    source_type="frigate",
                    name="postgres-adapter-002",
                    source_version="0.17.1-416a9b7",
                    adapter_version="0.2.0",
                    capabilities={"live_events": True},
                )
            )
            message = load_fixture_bundle(BUNDLE)[0]
            result = await FrigateIngestPipeline(session, source_instance_id=source.id).ingest(
                message, stream="postgres", cursor="0"
            )
            assert result.status == "persisted"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Observation)
                    .where(Observation.source_instance_id == source.id)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(OutboxEvent)
                    .where(OutboxEvent.dedupe_key.contains(str(source.id)))
                )
                == 1
            )
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
