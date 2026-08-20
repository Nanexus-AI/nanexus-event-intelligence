"""Configuration for the source-neutral Redis Stream pipeline."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_STREAM_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")


class RedisStreamConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stream: str = "nanexus:canonical-events"
    group: str = "nanexus:canonical-workers"
    dlq_stream: str = "nanexus:canonical-events:dlq"
    batch_size: int = Field(default=50, ge=1, le=1000)
    block_ms: int = Field(default=1000, ge=0, le=60_000)
    pending_idle_ms: int = Field(default=30_000, ge=0, le=3_600_000)
    max_delivery_attempts: int = Field(default=5, ge=1, le=100)
    max_inflight_messages: int = Field(default=100_000, ge=100, le=10_000_000)

    @field_validator("stream", "group", "dlq_stream")
    @classmethod
    def validate_redis_name(cls, value: str) -> str:
        if not _STREAM_NAME.fullmatch(value):
            raise ValueError("Redis stream and group names must use safe ASCII characters")
        return value
