import json
from pathlib import Path

import paho.mqtt.client as mqtt
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.adapters.frigate.config import FrigateMqttConfig
from nanexus_event_intelligence.adapters.frigate.live_worker import FrigateLiveIngestWorker
from nanexus_event_intelligence.adapters.frigate.replay import load_fixture_bundle
from nanexus_event_intelligence.persistence.models import Base, Observation, OutboxEvent

BUNDLE = Path(__file__).parents[4] / "fixtures" / "frigate" / "0.17" / "vehicle-lifecycle"


@pytest.mark.asyncio
async def test_live_worker_persists_before_message_can_be_acknowledged() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    worker = FrigateLiveIngestWorker(
        factory,
        FrigateMqttConfig(host="broker", client_id="live-worker-test"),
        source_name="live-worker-test",
        source_version="0.17.1",
    )
    worker._source_id = await worker._ensure_source()
    fixture = load_fixture_bundle(BUNDLE)[0]
    message = mqtt.MQTTMessage(mid=7, topic=fixture.topic.encode())
    message.payload = json.dumps(fixture.payload).encode()
    message.qos = 1
    message.retain = False

    await worker._ingest(message)

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Observation)) == 1
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_live_worker_quarantines_invalid_json_without_storing_body() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    worker = FrigateLiveIngestWorker(
        factory,
        FrigateMqttConfig(host="broker", client_id="invalid-worker-test"),
        source_name="invalid-worker-test",
        source_version="0.17.1",
    )
    worker._source_id = await worker._ensure_source()
    message = mqtt.MQTTMessage(mid=8, topic=b"frigate/events")
    message.payload = b"invalid-secret-body"
    message.qos = 1
    message.retain = False

    await worker._ingest(message)

    from nanexus_event_intelligence.persistence.models import RawSourceMessage

    async with factory() as session:
        raw = (await session.scalars(select(RawSourceMessage))).one()
        assert raw.quarantined
        assert "invalid-secret-body" not in str(raw.payload)
        assert "_invalid_payload_sha256" in raw.payload
    await engine.dispose()
