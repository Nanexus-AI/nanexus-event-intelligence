from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from nanexus_event_intelligence.persistence.models import Base, OutboxEvent
from nanexus_event_intelligence.pipeline.config import RedisStreamConfig
from nanexus_event_intelligence.pipeline.outbox import OutboxPublisher


class FakeOutboxRedis:
    def __init__(
        self, *, length: int = 0, fail_info: bool = False, fail_xadd: bool = False
    ) -> None:
        self.inflight = length
        self.fail_info = fail_info
        self.fail_xadd = fail_xadd
        self.messages: list[dict[str, str]] = []

    async def xinfo_groups(self, name: str) -> list[dict[str | bytes, object]]:
        if self.fail_info:
            raise ConnectionError("private connection detail")
        return [{"name": "nanexus:canonical-workers", "pending": self.inflight, "lag": 0}]

    async def xadd(self, name: str, fields: dict[str, str]) -> str:
        if self.fail_xadd:
            raise ConnectionError("private connection detail")
        self.messages.append(fields)
        return f"1-{len(self.messages)}"


async def make_factory() -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def add_outbox(factory: async_sessionmaker, dedupe_key: str = "canonical:test") -> None:
    async with factory.begin() as session:
        session.add(
            OutboxEvent(
                aggregate_type="object",
                aggregate_id=uuid4(),
                event_type="canonical.observation.persisted",
                schema_version="1.0",
                dedupe_key=dedupe_key,
                payload={"safe": True},
            )
        )


@pytest.mark.asyncio
async def test_publisher_marks_committed_outbox_after_xadd() -> None:
    engine, factory = await make_factory()
    redis = FakeOutboxRedis()
    await add_outbox(factory)

    result = await OutboxPublisher(factory, redis, RedisStreamConfig()).publish_batch()

    assert result.published == 1
    assert redis.messages[0]["dedupe_key"] == "canonical:test"
    async with factory() as session:
        persisted = (await session.scalars(select(OutboxEvent))).one()
        assert persisted.published_at is not None
        assert persisted.attempts == 1
        assert persisted.last_error is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_publisher_leaves_outbox_when_redis_is_unavailable() -> None:
    engine, factory = await make_factory()
    await add_outbox(factory)

    result = await OutboxPublisher(
        factory, FakeOutboxRedis(fail_info=True), RedisStreamConfig()
    ).publish_batch()

    assert result.failed == 1
    async with factory() as session:
        persisted = (await session.scalars(select(OutboxEvent))).one()
        assert persisted.published_at is None
        assert persisted.attempts == 0
        assert persisted.last_error is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_publisher_applies_stream_high_watermark_backpressure() -> None:
    engine, factory = await make_factory()
    await add_outbox(factory)
    config = RedisStreamConfig(max_inflight_messages=100)
    redis = FakeOutboxRedis(length=100)

    result = await OutboxPublisher(factory, redis, config).publish_batch()

    assert result.backpressured
    assert not redis.messages
    await engine.dispose()


@pytest.mark.asyncio
async def test_publisher_records_sanitized_xadd_failure_for_retry() -> None:
    engine, factory = await make_factory()
    await add_outbox(factory)

    result = await OutboxPublisher(
        factory, FakeOutboxRedis(fail_xadd=True), RedisStreamConfig()
    ).publish_batch()

    assert result.failed == 1
    async with factory() as session:
        persisted = (await session.scalars(select(OutboxEvent))).one()
        assert persisted.published_at is None
        assert persisted.attempts == 1
        assert persisted.last_error == "ConnectionError"
        assert "private connection detail" not in persisted.last_error
    await engine.dispose()


@pytest.mark.asyncio
async def test_publisher_backpressures_on_slowest_consumer_group() -> None:
    class MultiGroupRedis(FakeOutboxRedis):
        async def xinfo_groups(self, name: str) -> list[dict[str | bytes, object]]:
            del name
            return [
                {"name": "nanexus:canonical-workers", "pending": 0, "lag": 0},
                {"name": "nanexus:shadow-decisions", "pending": 20, "lag": 80},
            ]

    engine, factory = await make_factory()
    await add_outbox(factory)
    redis = MultiGroupRedis()
    result = await OutboxPublisher(
        factory, redis, RedisStreamConfig(max_inflight_messages=100)
    ).publish_batch()
    assert result.backpressured
    assert not redis.messages
    await engine.dispose()
