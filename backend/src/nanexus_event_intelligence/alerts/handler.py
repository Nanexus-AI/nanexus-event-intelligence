from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nanexus_event_intelligence.alerts.evaluator import evaluate
from nanexus_event_intelligence.alerts.models import AlertFact, ShadowPolicy
from nanexus_event_intelligence.alerts.policy import COMMUNITY_POLICY
from nanexus_event_intelligence.persistence.models import (
    Decision,
    Observation,
    ObservedObject,
    OutboxEvent,
)
from nanexus_event_intelligence.pipeline.worker import StreamEnvelope


class ShadowDecisionHandler:
    """Persist idempotent, notification-free rule decisions for canonical events."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        policy: ShadowPolicy = COMMUNITY_POLICY,
    ) -> None:
        self._session_factory = session_factory
        self._policy = policy

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
            observation = await session.scalar(
                select(Observation)
                .where(
                    Observation.source_instance_id == UUID(source_id),
                    Observation.dedupe_key == dedupe_key,
                )
                .with_for_update()
            )
            if observation is None:
                raise LookupError("canonical observation was not found")
            existing = await session.scalar(
                select(Decision).where(
                    Decision.subject_type == "observation",
                    Decision.subject_id == observation.id,
                    Decision.policy_id == self._policy.policy_id,
                    Decision.policy_version == self._policy.version,
                )
            )
            if existing is not None:
                return
            stationary = tuple(
                (
                    await session.scalars(
                        select(ObservedObject.stationary).where(
                            ObservedObject.observation_id == observation.id
                        )
                    )
                ).all()
            )
            result = evaluate(
                self._policy,
                AlertFact(
                    observation_id=observation.id,
                    event_kind=observation.event_kind,
                    lifecycle=observation.lifecycle,
                    occurred_at=observation.occurred_at,
                    labels=frozenset(observation.labels),
                    zones=frozenset(observation.zones),
                    object_stationary=stationary,
                ),
            )
            latest_revision = cast(
                int,
                (
                    await session.scalar(
                        select(func.coalesce(func.max(Decision.revision), 0)).where(
                            Decision.subject_id == observation.id
                        )
                    )
                )
                or 0,
            )
            decision = Decision(
                subject_type="observation",
                subject_id=observation.id,
                revision=latest_revision + 1,
                outcome=result.outcome,
                policy_id=result.policy_id,
                policy_version=result.policy_version,
                reasons=list(result.reasons),
                rule_trace=result.model_dump(mode="json"),
            )
            session.add(decision)
            await session.flush()
            session.add(
                OutboxEvent(
                    aggregate_type="decision",
                    aggregate_id=decision.id,
                    event_type="shadow.decision.created",
                    schema_version="1.0",
                    dedupe_key=f"shadow:{observation.id}:{result.policy_id}:{result.policy_version}",
                    payload={
                        "decision_id": str(decision.id),
                        "observation_id": str(observation.id),
                        "outcome": result.outcome,
                        "shadow": True,
                        "production_side_effects": False,
                    },
                )
            )
