import hashlib
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.adapters.frigate.pipeline import FrigateIngestPipeline
from nanexus_event_intelligence.adapters.frigate.replay import FixtureMessage, load_fixture_bundle
from nanexus_event_intelligence.core.contracts.processor_job import ProcessorJob as JobContract
from nanexus_event_intelligence.persistence.models import (
    Evidence,
    IngestCheckpoint,
    Observation,
    ObservedObject,
    OutboxEvent,
    ProcessorJob,
    RawSourceMessage,
    ReviewItem,
    ReviewObservation,
    SourceEntityMap,
    SourceInstance,
)
from nanexus_event_intelligence.persistence.repositories import SourceInstanceRepository

BUNDLE = Path(__file__).parents[4] / "fixtures" / "frigate" / "0.17" / "vehicle-lifecycle"


async def add_source(session: AsyncSession) -> SourceInstance:
    return await SourceInstanceRepository(session).add(
        SourceInstance(
            source_type="frigate",
            name="adapter-002",
            source_version="0.17.1-416a9b7",
            adapter_version="0.2.0",
            capabilities={"live_events": True},
        )
    )


async def count(session: AsyncSession, model: type[object]) -> int:
    return int((await session.scalar(select(func.count()).select_from(model))) or 0)


async def test_fixture_ingest_persists_complete_atomic_graph(session: AsyncSession) -> None:
    source = await add_source(session)
    pipeline = FrigateIngestPipeline(session, source_instance_id=source.id)
    results = await pipeline.ingest_fixture_bundle(str(BUNDLE), stream="fixture:vehicle")

    assert [result.status for result in results] == ["persisted"] * 6
    assert await count(session, RawSourceMessage) == 6
    assert await count(session, Observation) == 6
    assert await count(session, ObservedObject) == 3
    assert await count(session, OutboxEvent) == 6
    assert await count(session, ReviewItem) == 1
    assert await count(session, ReviewObservation) == 3
    assert await count(session, ProcessorJob) == 1
    assert await count(session, SourceEntityMap) == 2
    review = await session.scalar(select(ReviewItem))
    review_map = await session.scalar(
        select(SourceEntityMap).where(SourceEntityMap.namespace == "frigate.review")
    )
    review_observations = list(
        await session.scalars(
            select(Observation)
            .join(ReviewObservation, ReviewObservation.observation_id == Observation.id)
            .order_by(Observation.occurred_at)
        )
    )
    job = await session.scalar(select(ProcessorJob))
    assert review is not None and review.status == "ended"
    assert review.source_revision == review_observations[-1].source_revision
    assert review_map is not None and review_map.entity_type == "review_item"
    assert review_map.internal_entity_id == review.id
    assert all(item.id != review.id for item in review_observations)
    assert job is not None
    contract = JobContract.model_validate(job.payload)
    assert job.processor_type == "video_summary.caption_tags"
    assert job.subject_type == "review_item"
    assert job.subject_id == review.id
    assert job.subject_revision == review.source_revision
    assert {item.output_type for item in contract.requested_outputs} == {"caption", "tags"}
    granted_ids = {item.evidence_id for item in contract.evidence_refs}
    persisted_ids = set(await session.scalars(select(Evidence.id)))
    assert granted_ids and granted_ids.issubset(persisted_ids)
    checkpoint = await session.scalar(select(IngestCheckpoint))
    assert checkpoint is not None and checkpoint.cursor == "5"


async def test_review_lifecycle_revision_and_job_idempotency(session: AsyncSession) -> None:
    source = await add_source(session)
    messages = load_fixture_bundle(BUNDLE)
    pipeline = FrigateIngestPipeline(session, source_instance_id=source.id)

    await pipeline.ingest(messages[1], stream="reviews", cursor="0")
    assert await count(session, ReviewItem) == 1
    assert await count(session, ReviewObservation) == 1
    assert await count(session, ProcessorJob) == 0
    started_revision = await session.scalar(select(ReviewItem.source_revision))

    await pipeline.ingest(messages[3], stream="reviews", cursor="1")
    updated_revision = await session.scalar(select(ReviewItem.source_revision))
    assert updated_revision != started_revision
    assert await count(session, ReviewItem) == 1
    assert await count(session, ReviewObservation) == 2
    assert await count(session, ProcessorJob) == 0

    await pipeline.ingest(messages[5], stream="reviews", cursor="2")
    ended_revision = await session.scalar(select(ReviewItem.source_revision))
    assert ended_revision != updated_revision
    assert await count(session, ReviewObservation) == 3
    assert await count(session, ProcessorJob) == 1

    duplicate = await pipeline.ingest(messages[5], stream="reviews", cursor="3")
    assert duplicate.status == "duplicate"
    assert await count(session, ReviewItem) == 1
    assert await count(session, ReviewObservation) == 3
    assert await count(session, ProcessorJob) == 1

    revised_payload = deepcopy(messages[5].payload)
    after = revised_payload["after"]
    assert isinstance(after, dict)
    after["end_time"] = 1770000011
    revised = FixtureMessage(
        topic=messages[5].topic,
        observed_at=messages[5].observed_at + timedelta(seconds=1),
        qos=messages[5].qos,
        retain=messages[5].retain,
        payload_sha256="0" * 64,
        payload=revised_payload,
    )
    await pipeline.ingest(revised, stream="reviews", cursor="4")
    latest_revision = await session.scalar(select(ReviewItem.source_revision))
    assert latest_revision != ended_revision
    assert await count(session, ReviewItem) == 1
    assert await count(session, ReviewObservation) == 4
    assert await count(session, ProcessorJob) == 2
    assert set(await session.scalars(select(ProcessorJob.subject_revision))) == {
        ended_revision,
        latest_revision,
    }


async def test_restart_resumes_from_checkpoint(session: AsyncSession) -> None:
    source = await add_source(session)
    first = FrigateIngestPipeline(session, source_instance_id=source.id)
    initial = await first.ingest_fixture_bundle(
        str(BUNDLE), stream="fixture:restart", max_messages=3
    )
    restarted = FrigateIngestPipeline(session, source_instance_id=source.id)
    remaining = await restarted.ingest_fixture_bundle(str(BUNDLE), stream="fixture:restart")

    assert len(initial) == 3
    assert len(remaining) == 3
    assert await count(session, Observation) == 6


async def test_duplicate_does_not_repeat_observation_or_outbox(session: AsyncSession) -> None:
    source = await add_source(session)
    message = load_fixture_bundle(BUNDLE)[0]
    pipeline = FrigateIngestPipeline(session, source_instance_id=source.id)
    first = await pipeline.ingest(message, stream="mqtt:events", cursor="1")
    duplicate = await pipeline.ingest(message, stream="mqtt:events", cursor="2")

    assert first.status == "persisted"
    assert duplicate.status == "duplicate"
    assert await count(session, RawSourceMessage) == 1
    assert await count(session, Observation) == 1
    assert await count(session, OutboxEvent) == 1
    checkpoint = await session.scalar(select(IngestCheckpoint))
    assert checkpoint is not None and checkpoint.cursor == "2"


async def test_end_before_start_is_audited_without_state_regression(session: AsyncSession) -> None:
    source = await add_source(session)
    messages = load_fixture_bundle(BUNDLE)
    pipeline = FrigateIngestPipeline(session, source_instance_id=source.id)
    ended = await pipeline.ingest(messages[4], stream="reordered", cursor="0")
    started = await pipeline.ingest(messages[0], stream="reordered", cursor="1")

    assert ended.status == started.status == "persisted"
    history = await pipeline.observations.list_for_entity(source.id, "frigate.event", "object-1")
    assert [item.lifecycle for item in history] == ["started", "ended"]
    assert history[0].extensions["out_of_order"] is True
    assert history[0].extensions["after_terminal"] is True
    assert history[1].partial_history is True


async def test_invalid_message_is_quarantined_and_checkpointed(session: AsyncSession) -> None:
    source = await add_source(session)
    payload = {"type": "new", "password": "secret"}
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    message = FixtureMessage(
        topic="frigate/events",
        observed_at="2026-08-17T14:00:00Z",
        qos=1,
        retain=False,
        payload_sha256=hashlib.sha256(canonical).hexdigest(),
        payload=payload,
    )
    result = await FrigateIngestPipeline(session, source_instance_id=source.id).ingest(
        message, stream="mqtt:events", cursor="bad-1"
    )

    assert result.status == "quarantined"
    raw = await session.scalar(select(RawSourceMessage))
    assert raw is not None and raw.quarantined
    assert raw.payload["password"] == "[REDACTED]"
    assert "secret" not in (raw.quarantine_reason or "")
    assert await count(session, Observation) == 0
    assert await count(session, OutboxEvent) == 0


async def test_tracked_object_update_reuses_object_identity(session: AsyncSession) -> None:
    source = await add_source(session)
    base = load_fixture_bundle(BUNDLE)[0]
    update_payload = {
        "type": "classification",
        "id": "object-1",
        "camera": "camera_1",
        "timestamp": 1770000003,
        "model": "vehicle_type",
        "sub_label": "delivery_vehicle",
        "score": 0.87,
    }
    update = FixtureMessage(
        topic="frigate/tracked_object_update",
        observed_at="2026-08-17T14:00:03Z",
        qos=1,
        retain=False,
        payload_sha256="0" * 64,
        payload=update_payload,
    )
    pipeline = FrigateIngestPipeline(session, source_instance_id=source.id)
    await pipeline.ingest(base, stream="mqtt", cursor="0")
    result = await pipeline.ingest(update, stream="mqtt", cursor="1")

    assert result.status == "persisted"
    assert await count(session, SourceEntityMap) == 1
    history = await pipeline.observations.list_for_entity(source.id, "frigate.event", "object-1")
    assert history[-1].extensions["metadata_update_type"] == "classification"
    assert history[-1].extensions["classification"] == "delivery_vehicle"


async def test_caller_rollback_removes_entire_ingest_graph(session: AsyncSession) -> None:
    source = await add_source(session)
    await session.commit()
    message = load_fixture_bundle(BUNDLE)[0]
    await FrigateIngestPipeline(session, source_instance_id=source.id).ingest(
        message, stream="rollback", cursor="0"
    )
    await session.rollback()

    assert await count(session, RawSourceMessage) == 0
    assert await count(session, Observation) == 0
    assert await count(session, OutboxEvent) == 0
    assert await count(session, IngestCheckpoint) == 0
