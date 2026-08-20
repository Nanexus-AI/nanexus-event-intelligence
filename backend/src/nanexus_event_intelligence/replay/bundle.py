"""Replay bundle serialization and integrity validation."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from nanexus_event_intelligence.replay.models import ReplayEvent, ReplayManifest, ReplayRecord

MAX_MANIFEST_BYTES = 256 * 1024
MAX_EVENT_LINE_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 100_000
MAX_BUNDLE_BYTES = 512 * 1024 * 1024


class ReplayBundleError(ValueError):
    """Raised when a replay bundle is missing, malformed, or tampered."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def event_digest(event: ReplayEvent) -> str:
    return hashlib.sha256(canonical_json(event.model_dump(mode="json"))).hexdigest()


@dataclass(frozen=True, slots=True)
class ReplayBundle:
    manifest: ReplayManifest
    records: tuple[ReplayRecord, ...]


def load_replay_bundle(bundle_dir: Path) -> ReplayBundle:
    manifest_path = bundle_dir / "manifest.json"
    events_path = bundle_dir / "events.jsonl"
    if bundle_dir.is_symlink() or manifest_path.is_symlink() or events_path.is_symlink():
        raise ReplayBundleError("replay bundle cannot contain symbolic links")
    if not manifest_path.is_file() or not events_path.is_file():
        raise ReplayBundleError("replay bundle is incomplete")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ReplayBundleError("replay manifest exceeds size limit")
    try:
        manifest = ReplayManifest.model_validate_json(manifest_path.read_bytes())
    except (ValidationError, ValueError) as error:
        raise ReplayBundleError("invalid replay manifest") from error
    expected_bundle_id = uuid5(
        NAMESPACE_URL, f"nanexus-replay:{manifest.source_instance_id}:{manifest.events_sha256}"
    )
    if manifest.bundle_id != expected_bundle_id:
        raise ReplayBundleError("bundle ID does not match events hash")

    if events_path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ReplayBundleError("replay events file exceeds size limit")
    raw_events = events_path.read_bytes()
    if hashlib.sha256(raw_events).hexdigest() != manifest.events_sha256:
        raise ReplayBundleError("events bundle hash mismatch")
    lines = raw_events.splitlines()
    if len(lines) > MAX_EVENTS:
        raise ReplayBundleError("replay bundle contains too many events")
    records: list[ReplayRecord] = []
    for sequence, line in enumerate(lines):
        if len(line) > MAX_EVENT_LINE_BYTES:
            raise ReplayBundleError(f"event line {sequence} exceeds size limit")
        try:
            record = ReplayRecord.model_validate_json(line)
        except (ValidationError, ValueError) as error:
            raise ReplayBundleError(f"invalid event line {sequence}") from error
        if record.sequence != sequence:
            raise ReplayBundleError(f"event sequence mismatch at line {sequence}")
        if record.event.source_instance_id != manifest.source_instance_id:
            raise ReplayBundleError(f"source mismatch at line {sequence}")
        if event_digest(record.event) != record.event_sha256:
            raise ReplayBundleError(f"event hash mismatch at line {sequence}")
        records.append(record)
    if len(records) != manifest.event_count:
        raise ReplayBundleError("manifest event count mismatch")
    if records:
        ordered = sorted(
            records,
            key=lambda item: (
                item.event.occurred_at,
                item.event.observed_at,
                item.event.observation_id,
            ),
        )
        if records != ordered:
            raise ReplayBundleError("replay events are not in canonical order")
        if records[0].event.occurred_at != manifest.first_occurred_at:
            raise ReplayBundleError("manifest first event time mismatch")
        if records[-1].event.occurred_at != manifest.last_occurred_at:
            raise ReplayBundleError("manifest last event time mismatch")
    elif manifest.first_occurred_at is not None or manifest.last_occurred_at is not None:
        raise ReplayBundleError("empty bundle cannot declare event times")
    return ReplayBundle(manifest=manifest, records=tuple(records))
