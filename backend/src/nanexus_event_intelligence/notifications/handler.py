from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nanexus_event_intelligence.localization import system_text
from nanexus_event_intelligence.notifications.models import (
    DeliveryError,
    NotificationAdapter,
    NotificationMessage,
)
from nanexus_event_intelligence.persistence.models import (
    Action,
    Decision,
    Notification,
    Observation,
)
from nanexus_event_intelligence.pipeline.worker import StreamEnvelope


class CommunityNotificationHandler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapter: NotificationAdapter,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter

    async def __call__(self, envelope: StreamEnvelope) -> None:
        if envelope.event_type != "shadow.decision.created":
            return
        outcome_value = envelope.payload.get("outcome")
        if outcome_value not in {"send", "escalate"}:
            return
        outcome = cast(Literal["send", "escalate"], outcome_value)
        decision_id = UUID(str(envelope.payload.get("decision_id")))
        observation_id = UUID(str(envelope.payload.get("observation_id")))
        stage: Literal["initial", "escalated"] = "escalated" if outcome == "escalate" else "initial"
        key = f"community-webhook:{decision_id}:{stage}"

        async with self._session_factory.begin() as session:
            decision = await session.get(Decision, decision_id)
            observation = await session.get(Observation, observation_id)
            if decision is None or observation is None or decision.subject_id != observation.id:
                raise LookupError("notification subject was not found")
            action = await session.scalar(
                select(Action).where(Action.idempotency_key == key).with_for_update()
            )
            if action is not None and action.status in {"succeeded", "permanent_failure"}:
                return
            message = NotificationMessage(
                idempotency_key=key,
                decision_id=decision.id,
                observation_id=observation.id,
                outcome=outcome,
                stage=stage,
                title=system_text(
                    "notification.title.escalate"
                    if outcome == "escalate"
                    else "notification.title.send"
                ),
                body="; ".join(decision.reasons)[:1000]
                or system_text("notification.body.fallback"),
                source={
                    "event_kind": observation.event_kind,
                    "lifecycle": observation.lifecycle,
                    "labels": observation.labels,
                    "zones": observation.zones,
                    "occurred_at": observation.occurred_at.isoformat(),
                },
            )
            if action is None:
                action = Action(
                    decision_id=decision.id,
                    action_type="community_webhook",
                    idempotency_key=key,
                    payload=message.model_dump(mode="json"),
                )
                session.add(action)
                await session.flush()
                session.add(
                    Notification(
                        action_id=action.id,
                        channel="community_webhook",
                        stage=stage,
                        idempotency_key=key,
                    )
                )
            action.status = "running"
            action.attempts += 1
            action.last_error = None

        try:
            result = await self._adapter.deliver(message)
        except DeliveryError as error:
            await self._mark_failure(key, str(error), retryable=error.retryable)
            if error.retryable:
                raise
            return

        async with self._session_factory.begin() as session:
            action = await session.scalar(select(Action).where(Action.idempotency_key == key))
            if action is None:
                raise LookupError("notification action was not found")
            notification = await session.scalar(
                select(Notification).where(Notification.action_id == action.id)
            )
            if notification is None:
                raise LookupError("notification record was not found")
            action.status = "succeeded"
            notification.delivery_status = "succeeded"
            notification.external_message_id = result.external_message_id

    async def _mark_failure(self, key: str, message: str, *, retryable: bool) -> None:
        status = "retryable_failure" if retryable else "permanent_failure"
        async with self._session_factory.begin() as session:
            action = await session.scalar(select(Action).where(Action.idempotency_key == key))
            if action is None:
                raise LookupError("notification action was not found")
            notification = await session.scalar(
                select(Notification).where(Notification.action_id == action.id)
            )
            action.status = status
            action.last_error = message[:1000]
            if notification is not None:
                notification.delivery_status = status
