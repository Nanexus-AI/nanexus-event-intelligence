"""Deterministic replay engine with explicit sink safety."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from nanexus_event_intelligence.replay.bundle import ReplayBundle, canonical_json
from nanexus_event_intelligence.replay.models import ReplayEnvelope, ReplayEvent


class ReplaySafetyError(ValueError):
    """Raised when replay could invoke an unauthorized production side effect."""


class SinkSafety(StrEnum):
    DRY_RUN = "dry-run"
    TEST = "test"
    PRODUCTION = "production"


class ReplaySink(Protocol):
    safety: SinkSafety

    async def emit(self, envelope: ReplayEnvelope) -> None: ...


Sleeper = Callable[[float], Awaitable[None]]
Stepper = Callable[[int, ReplayEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    run_id: UUID
    bundle_id: UUID
    emitted: int
    output_sha256: str


class DryRunDigestSink:
    safety = SinkSafety.DRY_RUN

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self.count = 0

    async def emit(self, envelope: ReplayEnvelope) -> None:
        self._digest.update(canonical_json(envelope.model_dump(mode="json")) + b"\n")
        self.count += 1

    @property
    def output_sha256(self) -> str:
        return self._digest.hexdigest()


class ReplayEngine:
    def __init__(
        self,
        bundle: ReplayBundle,
        sink: ReplaySink,
        *,
        run_id: UUID,
        speed: float = 0,
        fixed_clock: datetime | None = None,
        stepper: Stepper | None = None,
        sleeper: Sleeper = asyncio.sleep,
        allow_production_side_effects: bool = False,
    ) -> None:
        if speed < 0:
            raise ValueError("speed cannot be negative")
        if stepper is not None and speed > 0:
            raise ValueError("step mode and timed speed are mutually exclusive")
        if fixed_clock is not None and fixed_clock.tzinfo is None:
            raise ValueError("fixed_clock must include a timezone")
        if sink.safety is SinkSafety.PRODUCTION and not allow_production_side_effects:
            raise ReplaySafetyError("production side effects are disabled for replay")
        self._bundle = bundle
        self._sink = sink
        self._run_id = run_id
        self._speed = speed
        self._fixed_clock = fixed_clock.astimezone(UTC) if fixed_clock else None
        self._stepper = stepper
        self._sleeper = sleeper

    async def run(self) -> ReplayResult:
        digest = hashlib.sha256()
        first_at = (
            self._as_utc(self._bundle.records[0].event.occurred_at)
            if self._bundle.records
            else None
        )
        previous_at: datetime | None = None
        emitted = 0
        for record in self._bundle.records:
            occurred_at = self._as_utc(record.event.occurred_at)
            if self._stepper is not None:
                await self._stepper(record.sequence, record.event)
            elif self._speed > 0 and previous_at is not None:
                await self._sleeper(
                    max(0.0, (occurred_at - previous_at).total_seconds()) / self._speed
                )
            replayed_at = occurred_at
            if self._fixed_clock is not None and first_at is not None:
                replayed_at = self._fixed_clock + (occurred_at - first_at)
            envelope = ReplayEnvelope(
                run_id=self._run_id,
                bundle_id=self._bundle.manifest.bundle_id,
                sequence=record.sequence,
                replayed_at=replayed_at,
                event=record.event,
            )
            await self._sink.emit(envelope)
            digest.update(canonical_json(envelope.model_dump(mode="json")) + b"\n")
            emitted += 1
            previous_at = occurred_at
        return ReplayResult(
            run_id=self._run_id,
            bundle_id=self._bundle.manifest.bundle_id,
            emitted=emitted,
            output_sha256=digest.hexdigest(),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
