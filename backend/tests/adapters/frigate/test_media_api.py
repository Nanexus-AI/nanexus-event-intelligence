from datetime import UTC, datetime
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.adapters.frigate.http_models import MediaResponse
from nanexus_event_intelligence.adapters.frigate.media_api import create_frigate_media_router
from nanexus_event_intelligence.config import Settings
from nanexus_event_intelligence.persistence.models import Base, Observation, SourceInstance


class FakeMediaClient:
    requested: list[str] = []

    async def __aenter__(self) -> "FakeMediaClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get_event_snapshot(self, event_id: str) -> MediaResponse:
        self.requested.append(event_id)
        return MediaResponse(content=b"jpeg", content_type="image/jpeg")


async def test_media_proxy_resolves_review_detection_without_exposing_source_url() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_id, observation_id = uuid4(), uuid4()
    async with factory.begin() as session:
        session.add(
            SourceInstance(
                id=source_id,
                source_type="frigate",
                name="source",
                adapter_version="1",
                capabilities={},
            )
        )
        session.add(
            Observation(
                id=observation_id,
                source_instance_id=source_id,
                source_namespace="frigate.review",
                source_entity_id="review-1",
                source_revision="1",
                dedupe_key="review-1:new",
                schema_version="1.0",
                event_kind="review",
                lifecycle="started",
                occurred_at=datetime.now(UTC),
                observed_at=datetime.now(UTC),
                labels=["car"],
                zones=[],
                extensions={
                    "links": [{"namespace": "frigate.event", "source_entity_id": "event-1"}]
                },
            )
        )
    app = FastAPI()
    app.state.session_factory = factory
    app.include_router(
        create_frigate_media_router(
            Settings(
                frigate_http_base_url="http://frigate.test", frigate_http_trusted_internal=True
            ),
            client_factory=lambda _: FakeMediaClient(),
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/events/{observation_id}/media/snapshot")
    assert response.status_code == 200
    assert response.content == b"jpeg"
    assert response.headers["cache-control"] == "private, no-store"
    assert "frigate.test" not in str(response.headers)
    assert FakeMediaClient.requested == ["event-1"]
    await engine.dispose()


async def test_media_proxy_is_disabled_without_http_configuration() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_id, observation_id = uuid4(), uuid4()
    async with factory.begin() as session:
        session.add(
            SourceInstance(
                id=source_id,
                source_type="frigate",
                name="source",
                adapter_version="1",
                capabilities={},
            )
        )
        session.add(
            Observation(
                id=observation_id,
                source_instance_id=source_id,
                source_namespace="frigate.event",
                source_entity_id="event-1",
                source_revision="1",
                dedupe_key="event-1:new",
                schema_version="1.0",
                event_kind="object",
                lifecycle="started",
                occurred_at=datetime.now(UTC),
                observed_at=datetime.now(UTC),
                labels=["car"],
                zones=[],
            )
        )
    app = FastAPI()
    app.state.session_factory = factory
    app.include_router(create_frigate_media_router(Settings()))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/events/{observation_id}/media/snapshot")
    assert response.status_code == 503
    await engine.dispose()
