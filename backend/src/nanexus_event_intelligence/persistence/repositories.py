from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.persistence.models import (
    IngestCheckpoint,
    Observation,
    OutboxEvent,
    RawSourceMessage,
    SourceEntityMap,
    SourceInstance,
    new_id,
)


class DuplicateObservationError(ValueError):
    """Raised when a source emits an already persisted canonical event."""


@dataclass(frozen=True, slots=True)
class NewObservation:
    source_instance_id: UUID
    source_namespace: str
    source_entity_id: str
    source_revision: str
    dedupe_key: str
    schema_version: str
    event_kind: str
    lifecycle: str
    occurred_at: datetime
    observed_at: datetime
    camera_id: UUID | None = None
    raw_message_id: UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    partial_history: bool = False
    labels: tuple[str, ...] = ()
    zones: tuple[str, ...] = ()
    extensions: dict[str, Any] | None = None


class SourceInstanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, source: SourceInstance) -> SourceInstance:
        self._session.add(source)
        await self._session.flush()
        return source

    async def get(self, source_id: UUID) -> SourceInstance | None:
        return await self._session.get(SourceInstance, source_id)

    async def get_by_type_and_name(self, source_type: str, name: str) -> SourceInstance | None:
        statement = select(SourceInstance).where(
            SourceInstance.source_type == source_type,
            SourceInstance.name == name,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


class SourceEntityMapRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, mapping: SourceEntityMap) -> SourceEntityMap:
        self._session.add(mapping)
        await self._session.flush()
        return mapping

    async def resolve(
        self, source_instance_id: UUID, namespace: str, source_entity_id: str
    ) -> SourceEntityMap | None:
        statement = select(SourceEntityMap).where(
            SourceEntityMap.source_instance_id == source_instance_id,
            SourceEntityMap.namespace == namespace,
            SourceEntityMap.source_entity_id == source_entity_id,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


class ObservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, data: NewObservation) -> Observation:
        observation = Observation(
            source_instance_id=data.source_instance_id,
            camera_id=data.camera_id,
            raw_message_id=data.raw_message_id,
            source_namespace=data.source_namespace,
            source_entity_id=data.source_entity_id,
            source_revision=data.source_revision,
            dedupe_key=data.dedupe_key,
            schema_version=data.schema_version,
            event_kind=data.event_kind,
            lifecycle=data.lifecycle,
            occurred_at=data.occurred_at,
            observed_at=data.observed_at,
            start_at=data.start_at,
            end_at=data.end_at,
            partial_history=data.partial_history,
            labels=list(data.labels),
            zones=list(data.zones),
            extensions=data.extensions or {},
        )
        self._session.add(observation)
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            raise DuplicateObservationError(data.dedupe_key) from error
        return observation

    async def get(self, observation_id: UUID) -> Observation | None:
        return await self._session.get(Observation, observation_id)

    async def get_by_dedupe_key(
        self, source_instance_id: UUID, dedupe_key: str
    ) -> Observation | None:
        statement = select(Observation).where(
            Observation.source_instance_id == source_instance_id,
            Observation.dedupe_key == dedupe_key,
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_for_entity(
        self,
        source_instance_id: UUID,
        namespace: str,
        source_entity_id: str,
    ) -> list[Observation]:
        statement = (
            select(Observation)
            .where(
                Observation.source_instance_id == source_instance_id,
                Observation.source_namespace == namespace,
                Observation.source_entity_id == source_entity_id,
            )
            .order_by(Observation.occurred_at, Observation.created_at)
        )
        return list((await self._session.scalars(statement)).all())


@dataclass(frozen=True, slots=True)
class NewRawSourceMessage:
    source_instance_id: UUID
    transport: str
    channel: str
    schema_version: str
    dedupe_key: str
    payload: dict[str, Any]
    payload_sha256: str
    observed_at: datetime
    quarantined: bool = False
    quarantine_reason: str | None = None


class RawSourceMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_dedupe_key(
        self, source_instance_id: UUID, dedupe_key: str
    ) -> RawSourceMessage | None:
        statement = select(RawSourceMessage).where(
            RawSourceMessage.source_instance_id == source_instance_id,
            RawSourceMessage.dedupe_key == dedupe_key,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def add(self, data: NewRawSourceMessage) -> RawSourceMessage:
        message = RawSourceMessage(
            source_instance_id=data.source_instance_id,
            transport=data.transport,
            channel=data.channel,
            schema_version=data.schema_version,
            dedupe_key=data.dedupe_key,
            payload=data.payload,
            payload_sha256=data.payload_sha256,
            observed_at=data.observed_at,
            quarantined=data.quarantined,
            quarantine_reason=data.quarantine_reason,
        )
        self._session.add(message)
        await self._session.flush()
        return message


class IngestCheckpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, source_instance_id: UUID, stream: str) -> IngestCheckpoint | None:
        statement = select(IngestCheckpoint).where(
            IngestCheckpoint.source_instance_id == source_instance_id,
            IngestCheckpoint.stream == stream,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def advance(self, source_instance_id: UUID, stream: str, cursor: str) -> IngestCheckpoint:
        checkpoint = await self.get(source_instance_id, stream)
        if checkpoint is None:
            checkpoint = IngestCheckpoint(
                source_instance_id=source_instance_id, stream=stream, cursor=cursor
            )
            self._session.add(checkpoint)
        else:
            checkpoint.cursor = cursor
        await self._session.flush()
        return checkpoint


class OutboxEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_dedupe_key(self, dedupe_key: str) -> OutboxEvent | None:
        statement = select(OutboxEvent).where(OutboxEvent.dedupe_key == dedupe_key)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def add(self, event: OutboxEvent) -> OutboxEvent:
        self._session.add(event)
        await self._session.flush()
        return event


async def resolve_or_create_entity_mapping(
    session: AsyncSession,
    *,
    source_instance_id: UUID,
    namespace: str,
    source_entity_id: str,
    entity_type: str,
) -> SourceEntityMap:
    repository = SourceEntityMapRepository(session)
    existing = await repository.resolve(source_instance_id, namespace, source_entity_id)
    if existing is not None:
        return existing
    return await repository.add(
        SourceEntityMap(
            source_instance_id=source_instance_id,
            namespace=namespace,
            source_entity_id=source_entity_id,
            entity_type=entity_type,
            internal_entity_id=new_id(),
        )
    )
