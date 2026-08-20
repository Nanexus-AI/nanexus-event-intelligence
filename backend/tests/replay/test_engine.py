from datetime import UTC, datetime
from uuid import UUID

import pytest

from nanexus_event_intelligence.replay.bundle import ReplayBundle
from nanexus_event_intelligence.replay.engine import (
    DryRunDigestSink,
    ReplayEngine,
    ReplaySafetyError,
    SinkSafety,
)
from nanexus_event_intelligence.replay.models import ReplayEvent, ReplayManifest, ReplayRecord

RUN_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2270")
BUNDLE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2271")
SOURCE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2260")
BASE_TIME = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
FIXED_CLOCK = datetime(2030, 1, 1, tzinfo=UTC)


def bundle() -> ReplayBundle:
    records = tuple(
        ReplayRecord(
            sequence=index,
            event_sha256="0" * 64,
            event=ReplayEvent(
                observation_id=UUID(f"0198b75e-052b-7d4a-9185-d3ea9c2d22{80 + index}"),
                source_instance_id=SOURCE_ID,
                source_namespace="object",
                source_entity_id="vehicle-1",
                source_revision=str(index),
                dedupe_key=f"event:{index}",
                schema_version="1.0",
                event_kind="object",
                lifecycle="updated",
                occurred_at=BASE_TIME.replace(second=index * 10),
                observed_at=BASE_TIME.replace(second=index * 10),
            ),
        )
        for index in range(3)
    )
    return ReplayBundle(
        manifest=ReplayManifest(
            bundle_id=BUNDLE_ID,
            source_instance_id=SOURCE_ID,
            source_type="frigate",
            exported_at=BASE_TIME,
            event_count=3,
            first_occurred_at=records[0].event.occurred_at,
            last_occurred_at=records[-1].event.occurred_at,
            events_sha256="1" * 64,
        ),
        records=records,
    )


@pytest.mark.asyncio
async def test_fixed_clock_and_run_id_produce_identical_output() -> None:
    first_sink = DryRunDigestSink()
    second_sink = DryRunDigestSink()
    first = await ReplayEngine(bundle(), first_sink, run_id=RUN_ID, fixed_clock=FIXED_CLOCK).run()
    second = await ReplayEngine(bundle(), second_sink, run_id=RUN_ID, fixed_clock=FIXED_CLOCK).run()

    assert first.output_sha256 == second.output_sha256
    assert first.output_sha256 == first_sink.output_sha256
    assert first.emitted == 3


@pytest.mark.asyncio
async def test_speed_scales_original_event_delays() -> None:
    delays: list[float] = []

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    await ReplayEngine(bundle(), DryRunDigestSink(), run_id=RUN_ID, speed=2, sleeper=sleeper).run()
    assert delays == [5.0, 5.0]


@pytest.mark.asyncio
async def test_stepper_releases_each_event_without_sleeping() -> None:
    stepped: list[int] = []

    async def stepper(sequence: int, event: ReplayEvent) -> None:
        del event
        stepped.append(sequence)

    await ReplayEngine(bundle(), DryRunDigestSink(), run_id=RUN_ID, stepper=stepper).run()
    assert stepped == [0, 1, 2]


class ProductionSink:
    safety = SinkSafety.PRODUCTION

    async def emit(self, envelope: object) -> None:
        raise AssertionError("production sink must never be called")


def test_production_sink_is_rejected_by_default() -> None:
    with pytest.raises(ReplaySafetyError, match="disabled"):
        ReplayEngine(bundle(), ProductionSink(), run_id=RUN_ID)


def test_step_and_speed_are_mutually_exclusive() -> None:
    async def stepper(sequence: int, event: ReplayEvent) -> None:
        del sequence, event

    with pytest.raises(ValueError, match="mutually exclusive"):
        ReplayEngine(bundle(), DryRunDigestSink(), run_id=RUN_ID, speed=1, stepper=stepper)
