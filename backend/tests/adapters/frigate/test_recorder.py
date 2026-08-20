from pathlib import Path
from typing import Any

import pytest

from nanexus_event_intelligence.adapters.frigate.config import FrigateMqttConfig
from nanexus_event_intelligence.adapters.frigate.recorder import FrigateFixtureRecorder


class FakeMessage:
    topic = "frigate/reviews"
    payload = b'{"type":"new","after":{"id":"review-1"}}'
    qos = 1
    retain = False


class FakeMessages:
    async def __anext__(self) -> FakeMessage:
        return FakeMessage()


class FakeClient:
    def __init__(self) -> None:
        self.messages = FakeMessages()
        self.subscriptions: list[tuple[str, int]] = []

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def subscribe(self, topic: str, *, qos: int) -> None:
        self.subscriptions.append((topic, qos))


@pytest.mark.asyncio
async def test_recorder_subscribes_and_writes_messages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = FakeClient()

    def client_factory(**_kwargs: Any) -> FakeClient:
        return client

    monkeypatch.setattr(
        "nanexus_event_intelligence.adapters.frigate.recorder.aiomqtt.Client", client_factory
    )
    config = FrigateMqttConfig(host="mqtt.local")
    count = await FrigateFixtureRecorder(config).record(
        tmp_path / "capture", source_version="0.17.1", max_messages=2
    )

    assert count == 2
    assert client.subscriptions == [(topic, 1) for topic in config.recording_topics]
    assert len((tmp_path / "capture" / "messages.jsonl").read_text().splitlines()) == 2


class FailingClient(FakeClient):
    async def __aenter__(self) -> "FailingClient":
        from aiomqtt import MqttError

        raise MqttError("connection lost")


@pytest.mark.asyncio
async def test_recorder_reconnects_after_transport_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clients = iter([FailingClient(), FakeClient()])
    sleeps: list[float] = []

    def client_factory(**_kwargs: Any) -> FakeClient:
        return next(clients)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(
        "nanexus_event_intelligence.adapters.frigate.recorder.aiomqtt.Client", client_factory
    )
    monkeypatch.setattr(
        "nanexus_event_intelligence.adapters.frigate.recorder.asyncio.sleep", fake_sleep
    )
    config = FrigateMqttConfig(host="mqtt.local", reconnect_delay_seconds=0.01)
    count = await FrigateFixtureRecorder(config).record(
        tmp_path / "capture", source_version="0.17.1", max_messages=1
    )
    assert count == 1
    assert sleeps == [0.01]
