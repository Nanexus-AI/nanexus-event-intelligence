from datetime import UTC, datetime
from uuid import UUID

import pytest

from nanexus_event_intelligence.alerts.replay import ShadowDecisionDryRunSink
from nanexus_event_intelligence.replay.bundle import ReplayBundle
from nanexus_event_intelligence.replay.engine import ReplayEngine
from nanexus_event_intelligence.replay.models import ReplayEvent, ReplayManifest, ReplayRecord

RUN_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2270")
BUNDLE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2271")
SOURCE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2260")
OBSERVATION_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2280")
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def replay_bundle() -> ReplayBundle:
    record = ReplayRecord(
        sequence=0,
        event_sha256="0" * 64,
        event=ReplayEvent(
            observation_id=OBSERVATION_ID,
            source_instance_id=SOURCE_ID,
            source_namespace="object",
            source_entity_id="vehicle-1",
            source_revision="1",
            dedupe_key="event:1",
            schema_version="1.0",
            event_kind="object",
            lifecycle="updated",
            occurred_at=NOW,
            observed_at=NOW,
        ),
    )
    return ReplayBundle(
        manifest=ReplayManifest(
            bundle_id=BUNDLE_ID,
            source_instance_id=SOURCE_ID,
            source_type="frigate",
            exported_at=NOW,
            event_count=1,
            first_occurred_at=NOW,
            last_occurred_at=NOW,
            events_sha256="1" * 64,
        ),
        records=(record,),
    )


@pytest.mark.asyncio
async def test_shadow_decisions_are_deterministic_and_side_effect_free_in_replay() -> None:
    first_sink = ShadowDecisionDryRunSink()
    second_sink = ShadowDecisionDryRunSink()
    first = await ReplayEngine(replay_bundle(), first_sink, run_id=RUN_ID, fixed_clock=NOW).run()
    second = await ReplayEngine(replay_bundle(), second_sink, run_id=RUN_ID, fixed_clock=NOW).run()
    assert first.output_sha256 == second.output_sha256
    assert first_sink.output_sha256 == second_sink.output_sha256
    assert [item.outcome for item in first_sink.evaluations] == ["no_action"]
