import httpx
import pytest
from pydantic import ValidationError

from nanexus_event_intelligence.notifications.models import DeliveryError, NotificationMessage
from nanexus_event_intelligence.notifications.webhook import (
    WebhookNotificationAdapter,
    WebhookNotificationConfig,
)


def message() -> NotificationMessage:
    return NotificationMessage(
        idempotency_key="key-1",
        decision_id="00000000-0000-0000-0000-000000000001",
        observation_id="00000000-0000-0000-0000-000000000002",
        outcome="send",
        stage="initial",
        title="Event detected",
        body="person",
        source={"labels": ["person"]},
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/hook",
        "https://user:pass@example.test/hook",
        "https://example.test/hook?token=x",
        "file:///tmp/hook",
    ],
)
def test_config_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        WebhookNotificationConfig(url=url)


async def test_delivery_sends_contract_and_idempotency_header() -> None:
    async def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["idempotency-key"] == "key-1"
        assert request.headers["x-nanexus-webhook-secret"] == "secret"
        assert b'"schema_version":"1.0"' in request.content
        return httpx.Response(202, headers={"x-request-id": "external-1"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    adapter = WebhookNotificationAdapter(
        WebhookNotificationConfig(url="https://example.test/hook", secret="secret"),
        client=client,
    )
    result = await adapter.deliver(message())
    assert result.external_message_id == "external-1"
    await client.aclose()


@pytest.mark.parametrize("status,retryable", [(503, True), (429, True), (302, False), (400, False)])
async def test_delivery_classifies_failures(status: int, retryable: bool) -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    adapter = WebhookNotificationAdapter(
        WebhookNotificationConfig(url="https://example.test/hook"), client=client
    )
    with pytest.raises(DeliveryError) as captured:
        await adapter.deliver(message())
    assert captured.value.retryable is retryable
    assert "example.test" not in str(captured.value)
    await client.aclose()
