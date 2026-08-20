import json
from pathlib import Path
from uuid import UUID

import pytest

from nanexus_event_intelligence.adapters.frigate.normalizer import normalize_frigate_message
from nanexus_event_intelligence.adapters.frigate.replay import (
    FixtureIntegrityError,
    FixtureMessage,
    load_fixture_bundle,
    replay_fixture_bundle,
)

BUNDLE = Path(__file__).parents[4] / "fixtures" / "frigate" / "0.17" / "vehicle-lifecycle"
SOURCE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2260")


def test_real_structure_fixture_has_complete_vehicle_lifecycles() -> None:
    messages = load_fixture_bundle(BUNDLE)
    events = [
        normalize_frigate_message(
            topic=message.topic,
            payload=message.payload,
            source_instance_id=SOURCE_ID,
            camera_ids={},
            observed_at=message.observed_at,
        )
        for message in messages
    ]
    assert len(messages) == 6
    assert {(event.event_kind, event.lifecycle) for event in events} == {
        ("object", "started"),
        ("object", "updated"),
        ("object", "ended"),
        ("review", "started"),
        ("review", "updated"),
        ("review", "ended"),
    }


def test_duplicates_and_out_of_order_keep_stable_identity() -> None:
    messages = load_fixture_bundle(BUNDLE)
    reordered = [messages[4], messages[0], messages[2], messages[0]]
    events = [
        normalize_frigate_message(
            topic=message.topic,
            payload=message.payload,
            source_instance_id=SOURCE_ID,
            camera_ids={},
            observed_at=message.observed_at,
        )
        for message in reordered
    ]
    assert events[0].lifecycle == "ended"
    assert events[1].event_id == events[3].event_id
    assert events[1].dedupe_key == events[3].dedupe_key


@pytest.mark.asyncio
async def test_replay_is_deterministic_and_preserves_order() -> None:
    emitted: list[FixtureMessage] = []

    async def sink(message: FixtureMessage) -> None:
        emitted.append(message)

    count = await replay_fixture_bundle(BUNDLE, sink)
    assert count == 6
    assert [message.payload["type"] for message in emitted] == [
        "new",
        "new",
        "update",
        "update",
        "end",
        "end",
    ]


def test_replay_rejects_payload_tampering(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "metadata.json").write_text('{"contains_secrets":false}')
    original = json.loads((BUNDLE / "messages.jsonl").read_text().splitlines()[0])
    original["payload"]["after"]["label"] = "tampered"
    (bundle / "messages.jsonl").write_text(json.dumps(original) + "\n")
    with pytest.raises(FixtureIntegrityError, match="payload hash mismatch"):
        load_fixture_bundle(bundle)
