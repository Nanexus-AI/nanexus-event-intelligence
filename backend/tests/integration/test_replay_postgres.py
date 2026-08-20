import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from nanexus_event_intelligence.persistence.models import Observation, SourceInstance
from nanexus_event_intelligence.replay.bundle import load_replay_bundle
from nanexus_event_intelligence.replay.engine import DryRunDigestSink, ReplayEngine
from nanexus_event_intelligence.replay.exporter import ObservationExporter


@pytest.mark.asyncio
async def test_postgres_export_load_and_fixed_clock_replay(tmp_path: Path) -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            source = SourceInstance(
                source_type="replay-integration",
                name=f"replay-{uuid4()}",
                adapter_version="1.0",
                capabilities={},
            )
            session.add(source)
            await session.flush()
            at = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
            session.add(
                Observation(
                    source_instance_id=source.id,
                    source_namespace="object",
                    source_entity_id="integration-1",
                    source_revision="1",
                    dedupe_key=f"replay:{uuid4()}",
                    schema_version="1.0",
                    event_kind="object",
                    lifecycle="started",
                    occurred_at=at,
                    observed_at=at,
                    labels=["car"],
                    zones=["entry"],
                    extensions={"token": "must-not-export"},
                )
            )
            await session.flush()
            output = tmp_path / "postgres-bundle"
            manifest = await ObservationExporter(session).export(
                source_instance_id=source.id,
                output_dir=output,
                exported_at=at,
            )
            bundle = load_replay_bundle(output)
            result = await ReplayEngine(
                bundle,
                DryRunDigestSink(),
                run_id=uuid4(),
                fixed_clock=datetime(2030, 1, 1, tzinfo=UTC),
            ).run()
            assert manifest.event_count == 1
            assert bundle.records[0].event.extensions["token"] == "[REDACTED]"
            assert result.emitted == 1
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
