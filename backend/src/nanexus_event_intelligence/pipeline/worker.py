"""Redis consumer-group worker with pending recovery, retries, and a DLQ."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict
from redis.exceptions import ResponseError

from nanexus_event_intelligence.pipeline.config import RedisStreamConfig


class RedisPipeline(Protocol):
    def xadd(self, name: str, fields: dict[str, str]) -> "RedisPipeline": ...

    def xack(self, name: str, groupname: str, *ids: str) -> "RedisPipeline": ...

    async def execute(self) -> list[object]: ...


class WorkerRedis(Protocol):
    async def xgroup_create(
        self, name: str, groupname: str, id: str = "$", mkstream: bool = False
    ) -> bool: ...

    async def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list[object]: ...

    async def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int | None = None,
    ) -> list[object]: ...

    async def xpending_range(
        self, name: str, groupname: str, min: str, max: str, count: int
    ) -> list[object]: ...

    async def xack(self, name: str, groupname: str, *ids: str) -> int: ...

    def pipeline(self, transaction: bool = True) -> RedisPipeline: ...


class StreamEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outbox_id: str
    dedupe_key: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    schema_version: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    processed: int = 0
    failed: int = 0
    dead_lettered: int = 0


MessageHandler = Callable[[StreamEnvelope], Awaitable[None]]


class RedisStreamWorker:
    """Consume canonical events with at-least-once handler invocation.

    The handler must make side effects idempotent using ``envelope.dedupe_key``.
    Failed messages remain pending until reclaimed; the final failed delivery is
    atomically added to the DLQ and acknowledged in the source stream.
    """

    def __init__(
        self,
        redis: WorkerRedis,
        config: RedisStreamConfig,
        *,
        consumer_name: str,
        handler: MessageHandler,
    ) -> None:
        if not consumer_name or len(consumer_name) > 128:
            raise ValueError("consumer_name must contain 1 to 128 characters")
        self._redis = redis
        self._config = config
        self._consumer_name = consumer_name
        self._handler = handler
        self._group_ready = False

    async def ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self._redis.xgroup_create(
                self._config.stream, self._config.group, id="0-0", mkstream=True
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise
        self._group_ready = True

    async def run_once(self) -> WorkerRunResult:
        await self.ensure_group()
        messages = await self._recover_pending()
        if not messages:
            response = await self._redis.xreadgroup(
                self._config.group,
                self._consumer_name,
                {self._config.stream: ">"},
                count=self._config.batch_size,
                block=self._config.block_ms or None,
            )
            messages = self._extract_read_messages(response)

        processed = failed = dead_lettered = 0
        for message_id, fields in messages:
            try:
                envelope = self._decode(fields)
                await self._handler(envelope)
            except Exception as error:
                attempts = await self._delivery_count(message_id)
                if attempts >= self._config.max_delivery_attempts:
                    await self._dead_letter(message_id, fields, attempts, error)
                    dead_lettered += 1
                else:
                    failed += 1
                continue
            await self._redis.xack(self._config.stream, self._config.group, message_id)
            processed += 1
        return WorkerRunResult(processed=processed, failed=failed, dead_lettered=dead_lettered)

    async def _recover_pending(self) -> list[tuple[str, dict[str, str]]]:
        response = await self._redis.xautoclaim(
            self._config.stream,
            self._config.group,
            self._consumer_name,
            self._config.pending_idle_ms,
            start_id="0-0",
            count=self._config.batch_size,
        )
        if len(response) < 2:
            return []
        return self._normalize_messages(cast(list[object], response[1]))

    async def _delivery_count(self, message_id: str) -> int:
        pending = await self._redis.xpending_range(
            self._config.stream, self._config.group, message_id, message_id, 1
        )
        if not pending:
            return 1
        item = cast(dict[object, object], pending[0])
        value = item.get("times_delivered", item.get(b"times_delivered", 1))
        return int(cast(int | str | bytes, value))

    async def _dead_letter(
        self,
        message_id: str,
        fields: dict[str, str],
        attempts: int,
        error: Exception,
    ) -> None:
        dlq_fields = {
            **fields,
            "source_stream": self._config.stream,
            "source_message_id": message_id,
            "delivery_attempts": str(attempts),
            "error_type": type(error).__name__,
        }
        transaction = self._redis.pipeline(transaction=True)
        transaction.xadd(self._config.dlq_stream, dlq_fields)
        transaction.xack(self._config.stream, self._config.group, message_id)
        await transaction.execute()

    @staticmethod
    def _decode(fields: dict[str, str]) -> StreamEnvelope:
        values: dict[str, object] = dict(fields)
        values["payload"] = json.loads(fields["payload"])
        return StreamEnvelope.model_validate(values)

    @classmethod
    def _extract_read_messages(cls, response: list[object]) -> list[tuple[str, dict[str, str]]]:
        if not response:
            return []
        stream_entry = cast(list[object] | tuple[object, object], response[0])
        return cls._normalize_messages(cast(list[object], stream_entry[1]))

    @staticmethod
    def _normalize_messages(messages: list[object]) -> list[tuple[str, dict[str, str]]]:
        normalized: list[tuple[str, dict[str, str]]] = []
        for raw in messages:
            message_id, raw_fields = cast(tuple[object, object] | list[object], raw)
            identifier = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
            fields: dict[str, str] = {}
            for key, value in cast(dict[object, object], raw_fields).items():
                text_key = key.decode() if isinstance(key, bytes) else str(key)
                text_value = value.decode() if isinstance(value, bytes) else str(value)
                fields[text_key] = text_value
            normalized.append((identifier, fields))
        return normalized
