"""Export canonical observations from SQLAlchemy storage to a replay bundle."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.persistence.models import Observation, SourceInstance
from nanexus_event_intelligence.replay.bundle import MAX_EVENTS, canonical_json, event_digest
from nanexus_event_intelligence.replay.models import ReplayEvent, ReplayManifest, ReplayRecord
from nanexus_event_intelligence.replay.privacy import sanitize_export


class ReplayExportError(ValueError):
    """Raised when an export request is unsafe or cannot be fulfilled."""


class ObservationExporter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def export(
        self,
        *,
        source_instance_id: UUID,
        output_dir: Path,
        exported_at: datetime,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        limit: int = MAX_EVENTS,
    ) -> ReplayManifest:
        for name, value in (
            ("exported_at", exported_at),
            ("occurred_from", occurred_from),
            ("occurred_to", occurred_to),
        ):
            if value is not None and value.tzinfo is None:
                raise ReplayExportError(f"{name} must include a timezone")
        if limit < 1 or limit > MAX_EVENTS:
            raise ReplayExportError(f"limit must be between 1 and {MAX_EVENTS}")
        if occurred_from and occurred_to and occurred_from > occurred_to:
            raise ReplayExportError("occurred_from must not be after occurred_to")
        if output_dir.exists():
            raise ReplayExportError("output directory already exists")
        source = await self._session.get(SourceInstance, source_instance_id)
        if source is None:
            raise ReplayExportError("source instance was not found")

        statement = select(Observation).where(Observation.source_instance_id == source_instance_id)
        if occurred_from is not None:
            statement = statement.where(Observation.occurred_at >= occurred_from)
        if occurred_to is not None:
            statement = statement.where(Observation.occurred_at <= occurred_to)
        statement = statement.order_by(
            Observation.occurred_at,
            Observation.observed_at,
            Observation.id,
        ).limit(limit + 1)
        observations = list((await self._session.scalars(statement)).all())
        truncated = len(observations) > limit
        observations = observations[:limit]
        records = [self._record(sequence, item) for sequence, item in enumerate(observations)]
        events_bytes = b"".join(
            canonical_json(record.model_dump(mode="json")) + b"\n" for record in records
        )
        events_sha256 = hashlib.sha256(events_bytes).hexdigest()
        manifest = ReplayManifest(
            bundle_id=uuid5(NAMESPACE_URL, f"nanexus-replay:{source.id}:{events_sha256}"),
            source_instance_id=source.id,
            source_type=source.source_type,
            source_version=source.source_version,
            exported_at=exported_at,
            event_count=len(records),
            first_occurred_at=records[0].event.occurred_at if records else None,
            last_occurred_at=records[-1].event.occurred_at if records else None,
            events_sha256=events_sha256,
            truncated=truncated,
        )
        output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        events_path = output_dir / "events.jsonl"
        manifest_path = output_dir / "manifest.json"
        events_path.write_bytes(events_bytes)
        manifest_path.write_bytes(canonical_json(manifest.model_dump(mode="json")) + b"\n")
        events_path.chmod(0o600)
        manifest_path.chmod(0o600)
        return manifest

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _record(cls, sequence: int, observation: Observation) -> ReplayRecord:
        event = ReplayEvent(
            observation_id=observation.id,
            source_instance_id=observation.source_instance_id,
            source_namespace=observation.source_namespace,
            source_entity_id=observation.source_entity_id,
            source_revision=observation.source_revision,
            dedupe_key=observation.dedupe_key,
            schema_version=observation.schema_version,
            event_kind=observation.event_kind,
            lifecycle=observation.lifecycle,
            occurred_at=cls._as_utc(observation.occurred_at),
            observed_at=cls._as_utc(observation.observed_at),
            start_at=cls._as_utc(observation.start_at) if observation.start_at else None,
            end_at=cls._as_utc(observation.end_at) if observation.end_at else None,
            partial_history=observation.partial_history,
            labels=list(observation.labels),
            zones=list(observation.zones),
            extensions=sanitize_export(observation.extensions),
        )
        return ReplayRecord(sequence=sequence, event_sha256=event_digest(event), event=event)
