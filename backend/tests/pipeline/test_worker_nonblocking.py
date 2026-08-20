from typing import Any

from nanexus_event_intelligence.pipeline.config import RedisStreamConfig
from nanexus_event_intelligence.pipeline.worker import RedisStreamWorker


class EmptyRedis:
    def __init__(self) -> None:
        self.block: int | None = -1

    async def xgroup_create(
        self, name: str, groupname: str, id: str = "$", mkstream: bool = False
    ) -> bool:
        return True

    async def xautoclaim(self, *args: Any, **kwargs: Any) -> list[object]:
        return ["0-0", []]

    async def xreadgroup(self, *args: Any, **kwargs: Any) -> list[object]:
        self.block = kwargs["block"]
        return []

    async def xpending_range(self, *args: Any, **kwargs: Any) -> list[object]:
        return []

    async def xack(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def pipeline(self, transaction: bool = True) -> Any:
        raise AssertionError("pipeline is not used")


async def test_zero_block_uses_non_blocking_redis_read() -> None:
    redis = EmptyRedis()

    async def handler(_: Any) -> None:
        raise AssertionError("handler is not used")

    worker = RedisStreamWorker(
        redis,
        RedisStreamConfig(block_ms=0),
        consumer_name="test-worker",
        handler=handler,
    )
    result = await worker.run_once()
    assert result.processed == 0
    assert redis.block is None
