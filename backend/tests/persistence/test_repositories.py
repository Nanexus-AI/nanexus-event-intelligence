from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.persistence.models import SourceEntityMap, SourceInstance
from nanexus_event_intelligence.persistence.repositories import (
    DuplicateObservationError,
    NewObservation,
    ObservationRepository,
    SourceEntityMapRepository,
    SourceInstanceRepository,
)


async def add_source(session: AsyncSession) -> SourceInstance:
    return await SourceInstanceRepository(session).add(
        SourceInstance(
            source_type="frigate",
            name="pilot",
            source_version="0.17.1-416a9b7",
            adapter_version="0.1.0",
            capabilities={"live_events": True, "media_fetch": True},
        )
    )


async def test_source_repository_round_trip(session: AsyncSession) -> None:
    source = await add_source(session)
    loaded = await SourceInstanceRepository(session).get_by_type_and_name("frigate", "pilot")
    assert loaded is not None
    assert loaded.id == source.id
    assert loaded.source_version == "0.17.1-416a9b7"


async def test_source_entity_mapping_resolves_external_id(session: AsyncSession) -> None:
    source = await add_source(session)
    mapping = SourceEntityMap(
        source_instance_id=source.id,
        namespace="tracked_object",
        source_entity_id="171234.abc",
        entity_type="observation_subject",
        internal_entity_id=source.id,
    )
    await SourceEntityMapRepository(session).add(mapping)
    resolved = await SourceEntityMapRepository(session).resolve(
        source.id, "tracked_object", "171234.abc"
    )
    assert resolved is not None
    assert resolved.internal_entity_id == source.id


async def test_observations_are_idempotent_and_ordered(session: AsyncSession) -> None:
    source = await add_source(session)
    repository = ObservationRepository(session)
    now = datetime.now(UTC)
    later = NewObservation(
        source_instance_id=source.id,
        source_namespace="tracked_object",
        source_entity_id="object-1",
        source_revision="2",
        dedupe_key="object-1:update:2",
        schema_version="1.0",
        event_kind="object",
        lifecycle="updated",
        occurred_at=now + timedelta(seconds=1),
        observed_at=now + timedelta(seconds=1),
        labels=("person",),
    )
    earlier = NewObservation(
        source_instance_id=source.id,
        source_namespace="tracked_object",
        source_entity_id="object-1",
        source_revision="1",
        dedupe_key="object-1:start:1",
        schema_version="1.0",
        event_kind="object",
        lifecycle="started",
        occurred_at=now,
        observed_at=now,
        labels=("person",),
    )
    await repository.add(later)
    await repository.add(earlier)
    observations = await repository.list_for_entity(source.id, "tracked_object", "object-1")
    assert [item.lifecycle for item in observations] == ["started", "updated"]

    duplicate_session = session
    with pytest.raises(DuplicateObservationError):
        await ObservationRepository(duplicate_session).add(earlier)
