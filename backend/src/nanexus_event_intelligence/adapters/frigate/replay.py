"""Deterministic loading and replay of redacted Frigate fixture bundles."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FixtureIntegrityError(ValueError):
    pass


class FixtureMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: str
    observed_at: datetime
    qos: int = Field(ge=0, le=2)
    retain: bool
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload: dict[str, Any]


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest()


def load_fixture_bundle(bundle_dir: Path) -> list[FixtureMessage]:
    metadata_path = bundle_dir / "metadata.json"
    messages_path = bundle_dir / "messages.jsonl"
    if not metadata_path.is_file() or not messages_path.is_file():
        raise FixtureIntegrityError("fixture bundle is incomplete")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("contains_secrets") is not False:
        raise FixtureIntegrityError("fixture bundle is not marked secret-free")

    messages: list[FixtureMessage] = []
    for line_number, line in enumerate(messages_path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            message = FixtureMessage.model_validate_json(line)
        except ValueError as error:
            raise FixtureIntegrityError(f"invalid fixture line {line_number}") from error
        if _payload_hash(message.payload) != message.payload_sha256:
            raise FixtureIntegrityError(f"payload hash mismatch at line {line_number}")
        messages.append(message)
    return messages


FixtureSink = Callable[[FixtureMessage], Awaitable[None]]


async def replay_fixture_bundle(bundle_dir: Path, emit: FixtureSink, *, speed: float = 0) -> int:
    if speed < 0:
        raise ValueError("speed cannot be negative")
    messages = load_fixture_bundle(bundle_dir)
    previous_at: datetime | None = None
    for message in messages:
        if speed and previous_at is not None:
            delay = max(0.0, (message.observed_at - previous_at).total_seconds() / speed)
            await asyncio.sleep(delay)
        await emit(message)
        previous_at = message.observed_at
    return len(messages)
