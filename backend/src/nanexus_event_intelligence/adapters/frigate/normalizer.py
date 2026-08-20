"""Normalize Frigate MQTT messages into the vendor-neutral event envelope."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import ValidationError

from nanexus_event_intelligence.adapters.frigate.payloads import (
    LifecycleType,
    ObjectMessage,
    ReviewMessage,
    TrackedObjectUpdate,
)
from nanexus_event_intelligence.core.source_adapter import CanonicalSourceEvent

EVENT_NAMESPACE = UUID("b964f35c-3b98-5be7-b76d-9c6fd8867ea3")
LIFECYCLE: dict[LifecycleType, Literal["started", "updated", "ended"]] = {
    "new": "started",
    "update": "updated",
    "end": "ended",
}


class FrigateProtocolError(ValueError):
    pass


def _at(timestamp: float | None, fallback: datetime) -> datetime:
    return datetime.fromtimestamp(timestamp, UTC) if timestamp is not None else fallback


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _sub_labels(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else value


def normalize_frigate_message(
    *,
    topic: str,
    payload: dict[str, Any],
    source_instance_id: UUID,
    camera_ids: dict[str, UUID],
    observed_at: datetime,
) -> CanonicalSourceEvent:
    message_type: LifecycleType
    camera: str | None
    kind: Literal["review", "object"]
    extensions: dict[str, Any]
    try:
        if topic.endswith("/reviews"):
            model_review = ReviewMessage.model_validate(payload)
            review = model_review.after
            message_type = model_review.type
            namespace, kind = "frigate.review", "review"
            entity_id, camera = review.id, review.camera
            start_time, end_time = review.start_time, review.end_time
            revision_time = review.end_time or review.data.thumb_time or review.start_time
            event_occurred_at = _at(revision_time, observed_at)
            labels = sorted(set(review.data.objects + review.data.audio))
            zones = sorted(set(review.data.zones))
            objects: list[dict[str, Any]] = []
            links = [
                {"relation": "contains", "namespace": "frigate.event", "source_entity_id": item}
                for item in review.data.detections
            ]
            extensions = {"severity": review.severity} if review.severity else {}
        elif topic.endswith("/events"):
            model_object = ObjectMessage.model_validate(payload)
            tracked = model_object.after
            message_type = model_object.type
            namespace, kind = "frigate.event", "object"
            entity_id, camera = tracked.id, tracked.camera
            start_time, end_time = tracked.start_time, tracked.end_time
            revision_time = tracked.end_time or tracked.frame_time or tracked.start_time
            event_occurred_at = _at(revision_time, observed_at)
            labels = [tracked.label]
            zones = sorted(set(tracked.current_zones + tracked.entered_zones))
            objects = [
                {
                    "object_id": tracked.id,
                    "label": tracked.label,
                    "sub_labels": _sub_labels(tracked.sub_label),
                    "confidence": tracked.score,
                    "stationary": tracked.stationary,
                }
            ]
            links = []
            extensions = {
                key: value
                for key, value in {
                    "snapshot_available": tracked.has_snapshot,
                    "clip_available": tracked.has_clip,
                }.items()
                if value is not None
            }
        elif topic.endswith("/tracked_object_update"):
            update = TrackedObjectUpdate.model_validate(payload)
            message_type = "update"
            namespace, kind = "frigate.event", "object"
            entity_id, camera = update.id, update.camera
            start_time, end_time = None, None
            revision_time = update.timestamp if update.timestamp is not None else 0.0
            event_occurred_at = _at(update.timestamp, observed_at)
            labels, zones = [], []
            objects = []
            links = []
            extensions = {
                key: value
                for key, value in {
                    "metadata_update_type": update.type,
                    "description": update.description,
                    "recognized_name": update.name,
                    "license_plate": update.plate,
                    "score": update.score,
                    "model": update.model,
                    "classification": update.sub_label or update.attribute,
                }.items()
                if value is not None
            }
        else:
            raise FrigateProtocolError(f"unsupported Frigate event topic: {topic}")
    except ValidationError as error:
        raise FrigateProtocolError("invalid Frigate MQTT payload") from error

    payload_hash = _hash(payload)
    lifecycle = LIFECYCLE[message_type]
    revision = f"{revision_time:.6f}:{payload_hash[:12]}"
    dedupe_key = f"{source_instance_id}:{namespace}:{entity_id}:{lifecycle}:{revision}"
    if namespace == "frigate.event" and extensions.get("snapshot_available") is True:
        evidence = [
            {
                "media_type": "snapshot",
                "source_ref": f"frigate:event:{entity_id}:snapshot:{revision}",
                "captured_at": event_occurred_at,
                "privacy_class": "local_only",
                "availability": "available",
                "metadata_json": {"adapter": "frigate", "lazy_fetch": True},
            }
        ]
    elif namespace == "frigate.review":
        evidence = [
            {
                "media_type": "preview",
                "source_ref": f"frigate:review:{entity_id}:preview:{revision}",
                "captured_at": event_occurred_at,
                "privacy_class": "local_only",
                "availability": "available",
                "metadata_json": {"adapter": "frigate", "lazy_fetch": True},
            }
        ]
    else:
        evidence = []
    return CanonicalSourceEvent(
        event_id=uuid5(EVENT_NAMESPACE, dedupe_key),
        source_instance_id=source_instance_id,
        source_namespace=namespace,
        source_entity_id=entity_id,
        source_revision=revision,
        dedupe_key=dedupe_key,
        event_kind=kind,
        lifecycle=lifecycle,
        occurred_at=event_occurred_at,
        observed_at=observed_at,
        camera_id=camera_ids.get(camera) if camera is not None else None,
        start_at=_at(start_time, observed_at) if start_time is not None else None,
        end_at=_at(end_time, observed_at) if end_time is not None else None,
        partial_history=message_type != "new",
        labels=labels,
        zones=zones,
        objects=objects,
        evidence=evidence,
        links=links,
        raw_ref=f"sha256:{payload_hash}",
        extensions=extensions,
    )
