"""Transactional, state-aware Frigate to Canonical persistence pipeline."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.adapters.frigate.normalizer import (
    FrigateProtocolError,
    normalize_frigate_message,
)
from nanexus_event_intelligence.adapters.frigate.redaction import redact
from nanexus_event_intelligence.adapters.frigate.replay import FixtureMessage, load_fixture_bundle
from nanexus_event_intelligence.persistence.models import Evidence, ObservedObject, OutboxEvent
from nanexus_event_intelligence.persistence.repositories import (
    IngestCheckpointRepository,
    NewObservation,
    NewRawSourceMessage,
    ObservationRepository,
    OutboxEventRepository,
    RawSourceMessageRepository,
    resolve_or_create_entity_mapping,
)

IngestStatus = Literal["persisted", "duplicate", "quarantined", "ignored"]


@dataclass(frozen=True, slots=True)
class IngestResult:
    status: IngestStatus
    cursor: str
    observation_id: UUID | None = None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class FrigateIngestPipeline:
    def __init__(
        self,
        session: AsyncSession,
        *,
        source_instance_id: UUID,
        camera_ids: dict[str, UUID] | None = None,
    ) -> None:
        self.session = session
        self.source_instance_id = source_instance_id
        self.camera_ids = camera_ids or {}
        self.raw_messages = RawSourceMessageRepository(session)
        self.observations = ObservationRepository(session)
        self.checkpoints = IngestCheckpointRepository(session)

    async def ingest(self, message: FixtureMessage, *, stream: str, cursor: str) -> IngestResult:
        payload_hash = self._payload_hash(message.payload)
        raw_dedupe_key = f"mqtt:{message.topic}:{payload_hash}"
        existing_raw = await self.raw_messages.get_by_dedupe_key(
            self.source_instance_id, raw_dedupe_key
        )
        if existing_raw is not None:
            await self.checkpoints.advance(self.source_instance_id, stream, cursor)
            return IngestResult(status="duplicate", cursor=cursor)

        safe_payload = redact(message.payload)
        if not isinstance(safe_payload, dict):
            raise TypeError("redacted MQTT payload must remain an object")
        raw_data = NewRawSourceMessage(
            source_instance_id=self.source_instance_id,
            transport="mqtt",
            channel=message.topic,
            schema_version="frigate-0.17",
            dedupe_key=raw_dedupe_key,
            payload=safe_payload,
            payload_sha256=payload_hash,
            observed_at=message.observed_at,
        )

        if message.topic.endswith("/available"):
            await self.raw_messages.add(raw_data)
            await self.checkpoints.advance(self.source_instance_id, stream, cursor)
            return IngestResult(status="ignored", cursor=cursor)

        try:
            event = normalize_frigate_message(
                topic=message.topic,
                payload=safe_payload,
                source_instance_id=self.source_instance_id,
                camera_ids=self.camera_ids,
                observed_at=message.observed_at,
            )
        except FrigateProtocolError:
            quarantined = replace(
                raw_data, quarantined=True, quarantine_reason="invalid Frigate MQTT payload"
            )
            await self.raw_messages.add(quarantined)
            await self.checkpoints.advance(self.source_instance_id, stream, cursor)
            return IngestResult(status="quarantined", cursor=cursor)

        existing_observation = await self.observations.get_by_dedupe_key(
            self.source_instance_id, event.dedupe_key
        )
        if existing_observation is not None:
            await self.checkpoints.advance(self.source_instance_id, stream, cursor)
            return IngestResult(status="duplicate", cursor=cursor)

        raw_message = await self.raw_messages.add(raw_data)
        history = await self.observations.list_for_entity(
            self.source_instance_id, event.source_namespace, event.source_entity_id
        )
        has_start = any(item.lifecycle == "started" for item in history)
        terminal = [item for item in history if item.lifecycle in {"ended", "deleted"}]
        out_of_order = bool(
            history
            and _as_utc(event.occurred_at) < max(_as_utc(item.occurred_at) for item in history)
        )
        after_terminal = bool(terminal and event.lifecycle not in {"corrected", "deleted"})
        extensions = {
            **event.extensions,
            "links": event.links,
            "out_of_order": out_of_order,
            "after_terminal": after_terminal,
        }
        partial_history = event.lifecycle != "started" and not has_start
        event = event.model_copy(
            update={"partial_history": partial_history, "extensions": extensions}
        )
        mapping = await resolve_or_create_entity_mapping(
            self.session,
            source_instance_id=self.source_instance_id,
            namespace=event.source_namespace,
            source_entity_id=event.source_entity_id,
            entity_type=event.event_kind,
        )
        observation = await self.observations.add(
            NewObservation(
                source_instance_id=self.source_instance_id,
                camera_id=event.camera_id,
                raw_message_id=raw_message.id,
                source_namespace=event.source_namespace,
                source_entity_id=event.source_entity_id,
                source_revision=event.source_revision,
                dedupe_key=event.dedupe_key,
                schema_version=event.schema_version,
                event_kind=event.event_kind,
                lifecycle=event.lifecycle,
                occurred_at=event.occurred_at,
                observed_at=event.observed_at,
                start_at=event.start_at,
                end_at=event.end_at,
                partial_history=event.partial_history,
                labels=tuple(event.labels),
                zones=tuple(event.zones),
                extensions=event.extensions,
            )
        )
        for item in event.evidence:
            self.session.add(
                Evidence(
                    source_instance_id=self.source_instance_id,
                    observation_id=observation.id,
                    media_type=str(item["media_type"]),
                    source_ref=str(item["source_ref"]),
                    captured_at=item.get("captured_at"),
                    privacy_class=str(item.get("privacy_class", "local_only")),
                    availability=str(item.get("availability", "unknown")),
                    metadata_json=dict(item.get("metadata_json", {})),
                )
            )
        for item in event.objects:
            self.session.add(
                ObservedObject(
                    observation_id=observation.id,
                    object_key=str(item["object_id"]),
                    label=str(item["label"]),
                    sub_labels=list(item.get("sub_labels", [])),
                    confidence=item.get("confidence"),
                    stationary=item.get("stationary"),
                    track={},
                )
            )
        await OutboxEventRepository(self.session).add(
            OutboxEvent(
                aggregate_type=event.event_kind,
                aggregate_id=mapping.internal_entity_id,
                event_type="canonical.observation.persisted",
                schema_version=event.schema_version,
                dedupe_key=f"canonical:{event.dedupe_key}",
                payload={
                    "internal_entity_id": str(mapping.internal_entity_id),
                    "event": event.model_dump(mode="json"),
                },
            )
        )
        await self.checkpoints.advance(self.source_instance_id, stream, cursor)
        await self.session.flush()
        return IngestResult(status="persisted", cursor=cursor, observation_id=observation.id)

    @staticmethod
    def _payload_hash(payload: dict[str, object]) -> str:
        canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(canonical).hexdigest()

    async def ingest_fixture_bundle(
        self,
        bundle_dir: str,
        *,
        stream: str,
        max_messages: int | None = None,
    ) -> list[IngestResult]:
        from pathlib import Path

        messages = load_fixture_bundle(Path(bundle_dir))
        checkpoint = await self.checkpoints.get(self.source_instance_id, stream)
        start_index = int(checkpoint.cursor) + 1 if checkpoint is not None else 0
        stop_index = len(messages)
        if max_messages is not None:
            stop_index = min(stop_index, start_index + max_messages)
        results: list[IngestResult] = []
        for index in range(start_index, stop_index):
            results.append(await self.ingest(messages[index], stream=stream, cursor=str(index)))
        return results
