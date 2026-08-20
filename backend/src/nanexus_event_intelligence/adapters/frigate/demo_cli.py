import argparse
import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nanexus_event_intelligence.adapters.frigate.pipeline import FrigateIngestPipeline
from nanexus_event_intelligence.alerts.replay import ShadowDecisionDryRunSink
from nanexus_event_intelligence.config import get_settings
from nanexus_event_intelligence.localization import system_text
from nanexus_event_intelligence.persistence.database import create_engine, create_session_factory
from nanexus_event_intelligence.persistence.models import (
    Action,
    Camera,
    Decision,
    Notification,
    Observation,
    SourceInstance,
)
from nanexus_event_intelligence.replay.bundle import load_replay_bundle
from nanexus_event_intelligence.replay.engine import ReplayEngine
from nanexus_event_intelligence.replay.exporter import ObservationExporter

SOURCE_NAME = "community-demo-frigate"
STREAM_NAME = "community-demo:vehicle-lifecycle:v1"
FIXED_EXPORTED_AT = datetime(2030, 1, 1, tzinfo=UTC)
FIXED_REPLAY_CLOCK = datetime(2031, 1, 1, tzinfo=UTC)
FIXED_RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
EXPECTED_EVENTS = 6


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Run the repeatable Nanexus Community Demo")
    root.add_argument(
        "--fixture",
        type=Path,
        default=Path("/demo-fixtures/frigate/0.17/vehicle-lifecycle"),
    )
    root.add_argument("--timeout", type=float, default=45.0)
    return root


async def seed(
    factory: async_sessionmaker[AsyncSession], fixture: Path
) -> tuple[UUID, dict[str, int]]:
    async with factory.begin() as session:
        source = await session.scalar(
            select(SourceInstance).where(
                SourceInstance.source_type == "frigate", SourceInstance.name == SOURCE_NAME
            )
        )
        if source is None:
            source = SourceInstance(
                source_type="frigate",
                name=SOURCE_NAME,
                source_version="0.17.1-416a9b7",
                adapter_version="community-demo-1.0",
                capabilities={"fixture_replay": True, "production_side_effects": False},
                health_status="healthy",
            )
            session.add(source)
            await session.flush()
        camera = await session.scalar(
            select(Camera).where(Camera.site_id == "community-demo", Camera.name == "camera_1")
        )
        if camera is None:
            camera = Camera(
                site_id="community-demo",
                name="camera_1",
                display_name=system_text("demo.camera.entry"),
                timezone="UTC",
                zones=["entrance"],
                privacy_policy={"synthetic_fixture": True},
            )
            session.add(camera)
            await session.flush()
        results = await FrigateIngestPipeline(
            session,
            source_instance_id=source.id,
            camera_ids={"camera_1": camera.id},
        ).ingest_fixture_bundle(str(fixture), stream=STREAM_NAME)
        return source.id, {
            value: sum(item.status == value for item in results)
            for value in ("persisted", "duplicate", "quarantined", "ignored")
        }


async def snapshot(factory: async_sessionmaker[AsyncSession], source_id: UUID) -> dict[str, object]:
    async with factory() as session:
        observations = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(Observation)
                    .where(Observation.source_instance_id == source_id)
                )
            )
            or 0
        )
        processed = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(Observation)
                    .where(
                        Observation.source_instance_id == source_id,
                        Observation.processed_at.is_not(None),
                    )
                )
            )
            or 0
        )
        decision_rows = list(
            (
                await session.execute(
                    select(Decision.outcome)
                    .join(Observation, Observation.id == Decision.subject_id)
                    .where(
                        Decision.subject_type == "observation",
                        Observation.source_instance_id == source_id,
                    )
                    .order_by(Observation.occurred_at, Observation.id)
                )
            ).scalars()
        )
        delivered = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .join(Action, Action.id == Notification.action_id)
                    .join(Decision, Decision.id == Action.decision_id)
                    .join(Observation, Observation.id == Decision.subject_id)
                    .where(
                        Observation.source_instance_id == source_id,
                        Notification.delivery_status == "succeeded",
                    )
                )
            )
            or 0
        )
        return {
            "observations": observations,
            "processed": processed,
            "decisions": len(decision_rows),
            "outcomes": decision_rows,
            "notifications_succeeded": delivered,
        }


async def wait_for_closed_loop(
    factory: async_sessionmaker[AsyncSession], source_id: UUID, timeout: float
) -> dict[str, object]:
    if timeout <= 0 or timeout > 300:
        raise ValueError("timeout must be between 0 and 300 seconds")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        state = await snapshot(factory, source_id)
        if (
            state["observations"] == EXPECTED_EVENTS
            and state["processed"] == EXPECTED_EVENTS
            and state["decisions"] == EXPECTED_EVENTS
            and state["notifications_succeeded"] == EXPECTED_EVENTS
        ):
            return state
        if loop.time() >= deadline:
            raise TimeoutError(f"community demo did not converge: {state}")
        await asyncio.sleep(0.25)


async def replay_check(
    factory: async_sessionmaker[AsyncSession], source_id: UUID
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="nanexus-community-demo-") as directory:
        output = Path(directory) / "bundle"
        async with factory() as session:
            manifest = await ObservationExporter(session).export(
                source_instance_id=source_id,
                output_dir=output,
                exported_at=FIXED_EXPORTED_AT,
            )
        sink = ShadowDecisionDryRunSink()
        result = await ReplayEngine(
            load_replay_bundle(output),
            sink,
            run_id=FIXED_RUN_ID,
            fixed_clock=FIXED_REPLAY_CLOCK,
        ).run()
        return {
            "event_count": manifest.event_count,
            "production_side_effects": False,
            "outcomes": [item.outcome for item in sink.evaluations],
            "decision_sha256": sink.output_sha256,
            "replay_sha256": result.output_sha256,
        }


async def async_main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        source_id, ingest = await seed(factory, args.fixture)
        state = await wait_for_closed_loop(factory, source_id, args.timeout)
        replay = await replay_check(factory, source_id)
        if replay["event_count"] != EXPECTED_EVENTS or set(cast(list[str], replay["outcomes"])) != {
            "send"
        }:
            raise RuntimeError("deterministic replay result did not match the demo contract")
        print(
            json.dumps(
                {
                    "status": "community-demo-complete",
                    "source_id": str(source_id),
                    "ingest": ingest,
                    "closed_loop": state,
                    "replay": replay,
                    "ui": "http://localhost:5173",
                    "api": "http://localhost:8000/api/v1/events",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    finally:
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(async_main())
    except (OSError, SQLAlchemyError, TimeoutError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Community demo failed: {type(error).__name__}: {error}") from None


if __name__ == "__main__":
    main()
