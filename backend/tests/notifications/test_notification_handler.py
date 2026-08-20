from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.notifications.handler import CommunityNotificationHandler
from nanexus_event_intelligence.notifications.models import (
    DeliveryError,
    DeliveryResult,
    NotificationMessage,
)
from nanexus_event_intelligence.persistence.models import (
    Action,
    Base,
    Decision,
    Notification,
    Observation,
    SourceInstance,
)
from nanexus_event_intelligence.pipeline.worker import StreamEnvelope


class RecordingAdapter:
    def __init__(self, failures: list[DeliveryError] | None = None) -> None:
        self.messages: list[NotificationMessage] = []
        self.failures = failures or []

    async def deliver(self, message: NotificationMessage) -> DeliveryResult:
        self.messages.append(message)
        if self.failures:
            raise self.failures.pop(0)
        return DeliveryResult(external_message_id="external-1")


async def setup(outcome: str = "send"):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    source_id, observation_id, decision_id = uuid4(), uuid4(), uuid4()
    async with factory.begin() as session:
        session.add(
            SourceInstance(
                id=source_id,
                source_type="test",
                name="source",
                adapter_version="1",
                capabilities={},
            )
        )
        session.add(
            Observation(
                id=observation_id,
                source_instance_id=source_id,
                source_namespace="object",
                source_entity_id="person-1",
                source_revision="1",
                dedupe_key="person-1:new",
                schema_version="1.0",
                event_kind="object",
                lifecycle="started",
                occurred_at=datetime.now(UTC),
                observed_at=datetime.now(UTC),
                labels=["person"],
                zones=["porch"],
            )
        )
        session.add(
            Decision(
                id=decision_id,
                subject_type="observation",
                subject_id=observation_id,
                revision=1,
                outcome=outcome,
                policy_id="community",
                policy_version="1",
                reasons=["Rule matched"],
            )
        )
    envelope = StreamEnvelope(
        outbox_id=str(uuid4()),
        dedupe_key=f"decision:{decision_id}",
        aggregate_type="decision",
        aggregate_id=str(decision_id),
        event_type="shadow.decision.created",
        schema_version="1.0",
        payload={
            "decision_id": str(decision_id),
            "observation_id": str(observation_id),
            "outcome": outcome,
            "shadow": True,
        },
    )
    return engine, factory, envelope


async def test_send_is_persisted_and_idempotent() -> None:
    engine, factory, envelope = await setup()
    adapter = RecordingAdapter()
    handler = CommunityNotificationHandler(factory, adapter)
    await handler(envelope)
    await handler(envelope)
    assert len(adapter.messages) == 1
    assert adapter.messages[0].title == "Event detected"
    assert adapter.messages[0].body == "Rule matched"
    async with factory() as session:
        action = await session.scalar(select(Action))
        notification = await session.scalar(select(Notification))
        assert action is not None and action.status == "succeeded" and action.attempts == 1
        assert notification is not None and notification.delivery_status == "succeeded"
        assert notification.external_message_id == "external-1"
    await engine.dispose()


@pytest.mark.parametrize("outcome", ["suppress", "no_action"])
async def test_non_delivery_outcomes_have_no_side_effects(outcome: str) -> None:
    engine, factory, envelope = await setup(outcome)
    adapter = RecordingAdapter()
    await CommunityNotificationHandler(factory, adapter)(envelope)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Action)) == 0
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0
    assert adapter.messages == []
    await engine.dispose()


async def test_retryable_failure_is_recorded_and_can_retry() -> None:
    engine, factory, envelope = await setup()
    adapter = RecordingAdapter([DeliveryError("temporary", retryable=True)])
    handler = CommunityNotificationHandler(factory, adapter)
    with pytest.raises(DeliveryError):
        await handler(envelope)
    async with factory() as session:
        action = await session.scalar(select(Action))
        assert action is not None and action.status == "retryable_failure"
    await handler(envelope)
    async with factory() as session:
        action = await session.scalar(select(Action))
        assert action is not None and action.status == "succeeded" and action.attempts == 2
    await engine.dispose()


async def test_permanent_failure_is_terminal() -> None:
    engine, factory, envelope = await setup("escalate")
    adapter = RecordingAdapter([DeliveryError("rejected", retryable=False)])
    handler = CommunityNotificationHandler(factory, adapter)
    await handler(envelope)
    await handler(envelope)
    assert len(adapter.messages) == 1
    assert adapter.messages[0].title == "Event requires attention"
    assert adapter.messages[0].body == "Rule matched"
    async with factory() as session:
        action = await session.scalar(select(Action))
        notification = await session.scalar(select(Notification))
        assert action is not None and action.status == "permanent_failure"
        assert notification is not None and notification.stage == "escalated"
    await engine.dispose()
