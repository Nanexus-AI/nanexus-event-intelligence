"""Built-in idempotent handlers for canonical stream events."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nanexus_event_intelligence.persistence.models import Observation
from nanexus_event_intelligence.pipeline.worker import StreamEnvelope


class ObservationProcessedHandler:
    """Mark a persisted observation processed after its stream delivery.

    The update is idempotent and commits before the worker acknowledges Redis.
    A future decision worker can consume the same stream with a separate group.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(self, envelope: StreamEnvelope) -> None:
        if envelope.event_type != "canonical.observation.persisted":
            return
        event = envelope.payload.get("event")
        if not isinstance(event, dict):
            raise ValueError("canonical event payload is missing")
        source_id = event.get("source_instance_id")
        dedupe_key = event.get("dedupe_key")
        if not isinstance(source_id, str) or not isinstance(dedupe_key, str):
            raise ValueError("canonical event identity is missing")

        async with self._session_factory.begin() as session:
            statement = (
                update(Observation)
                .where(
                    Observation.source_instance_id == UUID(source_id),
                    Observation.dedupe_key == dedupe_key,
                )
                .values(processed_at=datetime.now(UTC))
            )
            cursor = cast(CursorResult[Any], await session.execute(statement))
            if cursor.rowcount != 1:
                raise LookupError("canonical observation was not found")
