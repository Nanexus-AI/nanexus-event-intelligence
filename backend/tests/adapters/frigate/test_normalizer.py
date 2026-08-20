from datetime import UTC, datetime
from uuid import UUID

import pytest

from nanexus_event_intelligence.adapters.frigate.normalizer import (
    FrigateProtocolError,
    normalize_frigate_message,
)

SOURCE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2260")
CAMERA_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2261")
OBSERVED_AT = datetime(2026, 8, 17, 14, tzinfo=UTC)


def test_normalizes_realistic_review_and_detection_links() -> None:
    payload = {
        "type": "new",
        "before": None,
        "after": {
            "id": "review-1",
            "camera": "camera_1",
            "start_time": 1770000000.0,
            "end_time": None,
            "severity": "alert",
            "thumb_path": "/media/frigate/clips/review/example.webp",
            "data": {
                "detections": ["object-1"],
                "objects": ["car"],
                "zones": ["entrance"],
                "thumb_time": 1770000001.0,
                "future_field": "ignored",
            },
            "future_field": "ignored",
        },
    }
    event = normalize_frigate_message(
        topic="frigate/reviews",
        payload=payload,
        source_instance_id=SOURCE_ID,
        camera_ids={"camera_1": CAMERA_ID},
        observed_at=OBSERVED_AT,
    )
    assert event.source_namespace == "frigate.review"
    assert event.lifecycle == "started"
    assert event.labels == ["car"]
    assert event.zones == ["entrance"]
    assert event.camera_id == CAMERA_ID
    assert event.links == [
        {"relation": "contains", "namespace": "frigate.event", "source_entity_id": "object-1"}
    ]
    assert event.extensions == {"severity": "alert"}
    assert event.evidence[0]["media_type"] == "preview"
    assert event.evidence[0]["privacy_class"] == "local_only"


def test_object_normalization_is_deterministic_for_duplicates() -> None:
    payload = {
        "type": "end",
        "before": None,
        "after": {
            "id": "object-1",
            "camera": "camera_1",
            "start_time": 1770000000.0,
            "end_time": 1770000010.0,
            "frame_time": 1770000009.0,
            "label": "car",
            "sub_label": ["delivery"],
            "score": 0.91,
            "stationary": False,
            "current_zones": [],
            "entered_zones": ["entrance"],
            "has_snapshot": True,
            "has_clip": True,
            "path_data": [[1, 2], [3, 4]],
        },
    }
    first = normalize_frigate_message(
        topic="frigate/events",
        payload=payload,
        source_instance_id=SOURCE_ID,
        camera_ids={},
        observed_at=OBSERVED_AT,
    )
    second = normalize_frigate_message(
        topic="frigate/events",
        payload=payload,
        source_instance_id=SOURCE_ID,
        camera_ids={},
        observed_at=OBSERVED_AT,
    )
    assert first.event_id == second.event_id
    assert first.dedupe_key == second.dedupe_key
    assert first.lifecycle == "ended"
    assert first.labels == ["car"]
    assert first.zones == ["entrance"]
    assert first.camera_id is None
    assert first.objects[0]["confidence"] == 0.91
    assert first.extensions == {"snapshot_available": True, "clip_available": True}
    assert first.evidence[0]["media_type"] == "snapshot"
    assert "object-1" in first.evidence[0]["source_ref"]


def test_rejects_invalid_payload_without_echoing_it() -> None:
    with pytest.raises(FrigateProtocolError, match="invalid Frigate MQTT payload") as error:
        normalize_frigate_message(
            topic="frigate/events",
            payload={"password": "must-not-leak"},
            source_instance_id=SOURCE_ID,
            camera_ids={},
            observed_at=OBSERVED_AT,
        )
    assert "must-not-leak" not in str(error.value)


def test_rejects_non_event_topic() -> None:
    with pytest.raises(FrigateProtocolError, match="unsupported Frigate event topic"):
        normalize_frigate_message(
            topic="frigate/available",
            payload={"value": "online"},
            source_instance_id=SOURCE_ID,
            camera_ids={},
            observed_at=OBSERVED_AT,
        )


@pytest.mark.parametrize(
    ("payload", "expected_key"),
    [
        ({"type": "description", "id": "object-1", "description": "synthetic"}, "description"),
        (
            {
                "type": "face",
                "id": "object-1",
                "name": "synthetic",
                "score": 0.9,
                "camera": "camera_1",
                "timestamp": 1770000003,
            },
            "recognized_name",
        ),
        (
            {
                "type": "lpr",
                "id": "object-1",
                "plate": "SYNTH123",
                "score": 0.9,
                "camera": "camera_1",
                "timestamp": 1770000003,
            },
            "license_plate",
        ),
        (
            {
                "type": "classification",
                "id": "object-1",
                "model": "vehicle_type",
                "sub_label": "delivery_vehicle",
                "camera": "camera_1",
                "timestamp": 1770000003,
            },
            "classification",
        ),
    ],
)
def test_normalizes_tracked_object_metadata_updates(
    payload: dict[str, object], expected_key: str
) -> None:
    event = normalize_frigate_message(
        topic="frigate/tracked_object_update",
        payload=payload,
        source_instance_id=SOURCE_ID,
        camera_ids={"camera_1": CAMERA_ID},
        observed_at=OBSERVED_AT,
    )
    assert event.source_namespace == "frigate.event"
    assert event.source_entity_id == "object-1"
    assert event.lifecycle == "updated"
    assert event.extensions["metadata_update_type"] == payload["type"]
    assert expected_key in event.extensions
