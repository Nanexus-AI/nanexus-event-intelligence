from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.main import create_app
from nanexus_event_intelligence.persistence.models import (
    AuditRecord,
    Base,
    Camera,
    Evidence,
    Feedback,
    ObservedObject,
    RawSourceMessage,
    SourceInstance,
)
from nanexus_event_intelligence.persistence.repositories import (
    NewObservation,
    ObservationRepository,
)


async def test_event_list_detail_and_feedback_round_trip() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        source = SourceInstance(
            source_type="frigate",
            name="pilot",
            source_version="0.17.1",
            adapter_version="0.3.0",
            capabilities={},
        )
        camera = Camera(site_id="home", name="front", display_name="前门", timezone="UTC")
        session.add_all([source, camera])
        await session.flush()
        raw = RawSourceMessage(
            source_instance_id=source.id,
            transport="mqtt",
            channel="frigate/reviews",
            schema_version="frigate-0.17",
            dedupe_key="raw-1",
            payload={"type": "new", "password": "[REDACTED]"},
            payload_sha256="a" * 64,
            observed_at=now,
        )
        session.add(raw)
        await session.flush()
        event = await ObservationRepository(session).add(
            NewObservation(
                source_instance_id=source.id,
                camera_id=camera.id,
                raw_message_id=raw.id,
                source_namespace="frigate.review",
                source_entity_id="review-1",
                source_revision="1",
                dedupe_key="review-1:new",
                schema_version="1.0",
                event_kind="review",
                lifecycle="started",
                occurred_at=now,
                observed_at=now,
                labels=("person",),
                zones=("porch",),
                extensions={
                    "links": [{"namespace": "frigate.event", "source_entity_id": "object-1"}]
                },
            )
        )
        session.add_all(
            [
                ObservedObject(
                    observation_id=event.id, object_key="person-1", label="person", confidence=0.92
                ),
                Evidence(
                    source_instance_id=source.id,
                    observation_id=event.id,
                    media_type="snapshot",
                    source_ref="frigate:event/person-1/snapshot",
                    privacy_class="local_only",
                    availability="available",
                ),
            ]
        )
        event_id = event.id
        ended_at = now + timedelta(seconds=27)
        latest = await ObservationRepository(session).add(
            NewObservation(
                source_instance_id=source.id,
                camera_id=camera.id,
                source_namespace="frigate.review",
                source_entity_id="review-1",
                source_revision="2",
                dedupe_key="review-1:end",
                schema_version="1.0",
                event_kind="review",
                lifecycle="ended",
                occurred_at=ended_at,
                observed_at=ended_at,
                start_at=now,
                end_at=ended_at,
                labels=("person",),
                zones=("porch",),
                extensions={
                    "links": [{"namespace": "frigate.event", "source_entity_id": "object-1"}]
                },
            )
        )
        latest_id = latest.id
        for revision, lifecycle, occurred_at in (
            ("1", "started", now),
            ("2", "ended", ended_at),
        ):
            object_observation = await ObservationRepository(session).add(
                NewObservation(
                    source_instance_id=source.id,
                    camera_id=camera.id,
                    source_namespace="frigate.event",
                    source_entity_id="object-1",
                    source_revision=revision,
                    dedupe_key=f"object-1:{lifecycle}",
                    schema_version="1.0",
                    event_kind="object",
                    lifecycle=lifecycle,
                    occurred_at=occurred_at,
                    observed_at=occurred_at,
                    start_at=now,
                    end_at=ended_at if lifecycle == "ended" else None,
                    labels=("person",),
                    zones=("porch",) if lifecycle == "ended" else (),
                    extensions={"links": []},
                )
            )
            if lifecycle == "ended":
                session.add(
                    ObservedObject(
                        observation_id=object_observation.id,
                        object_key="person-1",
                        label="person",
                        confidence=0.92,
                    )
                )

    app = create_app(factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listing = await client.get(
            "/api/v1/events", params={"event_kind": "review", "label": "person"}
        )
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["camera_name"] == "前门"
        assert listing.json()["items"][0]["id"] == str(latest_id)
        assert listing.json()["items"][0]["observation_count"] == 2
        assert listing.json()["items"][0]["lifecycle"] == "ended"

        default_listing = await client.get("/api/v1/events")
        assert default_listing.json()["total"] == 1
        assert default_listing.json()["items"][0]["event_kind"] == "review"
        object_listing = await client.get("/api/v1/events", params={"event_kind": "object"})
        assert object_listing.json()["total"] == 1

        detail = await client.get(f"/api/v1/events/{event_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["raw_message"]["payload"]["password"] == "[REDACTED]"
        assert body["objects"][0]["confidence"] == 0.92
        assert body["evidence"][0]["availability"] == "available"
        assert body["observation_count"] == 2
        assert [item["lifecycle"] for item in body["timeline"]] == ["started", "ended"]
        assert {item["source_namespace"] for item in body["timeline"]} == {"frigate.event"}
        assert body["related_entity_ids"] == ["object-1"]
        assert body["last_occurred_at"].startswith(ended_at.replace(tzinfo=None).isoformat())

        first = await client.post(
            f"/api/v1/events/{event_id}/feedback",
            json={"verdict": "important", "reason": "需要提醒"},
        )
        assert first.status_code == 201
        second = await client.post(
            f"/api/v1/events/{event_id}/feedback", json={"verdict": "false_positive"}
        )
        assert second.status_code == 201
        assert second.json()["verdict"] == "false_positive"

        refreshed = await client.get(f"/api/v1/events/{event_id}")
        assert refreshed.json()["feedback"]["verdict"] == "false_positive"
        assert refreshed.json()["decisions"][0]["policy_id"] == "ui-feedback-anchor"

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Feedback)) == 2
        assert await session.scalar(select(func.count()).select_from(AuditRecord)) == 2
    await engine.dispose()


async def test_event_not_found_and_feedback_validation() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app(factory)
    transport = httpx.ASGITransport(app=app)
    missing = "00000000-0000-0000-0000-000000000001"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(f"/api/v1/events/{missing}")).status_code == 404
        invalid = await client.post(f"/api/v1/events/{missing}/feedback", json={"verdict": "wrong"})
        assert invalid.status_code == 422
    await engine.dispose()
