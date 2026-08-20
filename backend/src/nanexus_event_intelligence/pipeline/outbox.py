"""Transactional outbox publisher with bounded Redis backpressure."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from redis.exceptions import RedisError, ResponseError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nanexus_event_intelligence.persistence.models import OutboxEvent
from nanexus_event_intelligence.pipeline.config import RedisStreamConfig


class OutboxRedis(Protocol):
    async def xinfo_groups(self, name: str) -> list[dict[str | bytes, object]]: ...

    async def xadd(self, name: str, fields: dict[str, str]) -> str | bytes: ...


@dataclass(frozen=True, slots=True)
class OutboxPublishResult:
    published: int = 0
    failed: int = 0
    backpressured: bool = False


class OutboxPublisher:
    """Move committed outbox rows to Redis using at-least-once delivery.

    Rows are locked with SKIP LOCKED so multiple publishers can cooperate. A crash
    after XADD but before the database commit can publish a duplicate; consumers
    must therefore use ``dedupe_key`` for idempotent side effects.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: OutboxRedis,
        config: RedisStreamConfig,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._config = config

    async def publish_batch(self) -> OutboxPublishResult:
        try:
            if await self._inflight_count() >= self._config.max_inflight_messages:
                return OutboxPublishResult(backpressured=True)
        except RedisError:
            return OutboxPublishResult(failed=1)

        published = 0
        failed = 0
        async with self._session_factory() as session:
            async with session.begin():
                statement = (
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None))
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                    .limit(self._config.batch_size)
                    .with_for_update(skip_locked=True)
                )
                events = list((await session.scalars(statement)).all())
                for event in events:
                    event.attempts += 1
                    try:
                        await self._redis.xadd(self._config.stream, self._fields(event))
                    except RedisError as error:
                        event.last_error = type(error).__name__
                        failed += 1
                        break
                    event.published_at = datetime.now(UTC)
                    event.last_error = None
                    published += 1
        return OutboxPublishResult(published=published, failed=failed)

    async def _inflight_count(self) -> int:
        try:
            groups = await self._redis.xinfo_groups(self._config.stream)
        except ResponseError:
            return 0
        maximum = 0
        for group in groups:
            pending_value = group.get("pending", group.get(b"pending", 0))
            pending = int(cast(int | str | bytes, pending_value))
            lag_value = group.get("lag", group.get(b"lag", 0))
            lag = 0 if lag_value is None else int(cast(int | str | bytes, lag_value))
            maximum = max(maximum, pending + lag)
        return maximum

    @staticmethod
    def _fields(event: OutboxEvent) -> dict[str, str]:
        return {
            "outbox_id": str(event.id),
            "dedupe_key": event.dedupe_key,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "payload": json.dumps(event.payload, separators=(",", ":"), sort_keys=True),
        }
