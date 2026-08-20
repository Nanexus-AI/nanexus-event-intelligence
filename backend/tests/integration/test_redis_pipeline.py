import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.persistence.models import OutboxEvent
from nanexus_event_intelligence.pipeline.config import RedisStreamConfig
from nanexus_event_intelligence.pipeline.outbox import OutboxPublisher
from nanexus_event_intelligence.pipeline.worker import RedisStreamWorker, StreamEnvelope


@pytest.mark.asyncio
async def test_postgres_outbox_to_redis_worker_and_dlq() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    redis_url = os.environ.get("TEST_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("TEST_DATABASE_URL and TEST_REDIS_URL are required")

    suffix = uuid4().hex
    config = RedisStreamConfig(
        stream=f"test:canonical:{suffix}",
        group=f"test:workers:{suffix}",
        dlq_stream=f"test:dlq:{suffix}",
        block_ms=0,
        pending_idle_ms=0,
        max_delivery_attempts=2,
    )
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    redis: Redis = Redis.from_url(redis_url, decode_responses=True)
    dedupe_keys = [f"pipe-001:{suffix}:ok", f"pipe-001:{suffix}:fail"]
    try:
        async with factory.begin() as session:
            for key in dedupe_keys:
                session.add(
                    OutboxEvent(
                        aggregate_type="object",
                        aggregate_id=uuid4(),
                        event_type="canonical.observation.persisted",
                        schema_version="1.0",
                        dedupe_key=key,
                        payload={"dedupe_key": key},
                    )
                )

        publish_result = await OutboxPublisher(factory, redis, config).publish_batch()
        assert publish_result.published == 2

        handled: list[str] = []

        async def handler(envelope: StreamEnvelope) -> None:
            if envelope.dedupe_key.endswith(":fail"):
                raise RuntimeError("sensitive handler detail")
            handled.append(envelope.dedupe_key)

        first_worker = RedisStreamWorker(
            redis, config, consumer_name="worker-before-restart", handler=handler
        )
        first = await first_worker.run_once()
        assert first.processed == 1
        assert first.failed == 1
        assert handled == [dedupe_keys[0]]

        restarted_worker = RedisStreamWorker(
            redis, config, consumer_name="worker-after-restart", handler=handler
        )
        second = await restarted_worker.run_once()
        assert second.dead_lettered == 1

        dlq_entries = await redis.xrange(config.dlq_stream)
        assert len(dlq_entries) == 1
        _, dlq_fields = dlq_entries[0]
        assert dlq_fields["dedupe_key"] == dedupe_keys[1]
        assert dlq_fields["delivery_attempts"] == "2"
        assert dlq_fields["error_type"] == "RuntimeError"
        assert "sensitive handler detail" not in str(dlq_fields)

        pending = await redis.xpending(config.stream, config.group)
        assert pending["pending"] == 0
        async with factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(OutboxEvent).where(OutboxEvent.dedupe_key.in_(dedupe_keys))
                    )
                ).all()
            )
            assert all(row.published_at is not None for row in rows)
            assert all(row.attempts == 1 for row in rows)
    finally:
        await redis.delete(config.stream, config.dlq_stream)
        await redis.aclose()
        async with factory.begin() as session:
            await session.execute(
                delete(OutboxEvent).where(OutboxEvent.dedupe_key.in_(dedupe_keys))
            )
        await engine.dispose()
