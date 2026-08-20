import httpx

from nanexus_event_intelligence.demo.webhook_receiver import app


async def test_demo_webhook_accepts_valid_notification() -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    payload = {
        "schema_version": "1.0",
        "idempotency_key": "demo-key",
        "decision_id": "00000000-0000-0000-0000-000000000001",
        "observation_id": "00000000-0000-0000-0000-000000000002",
        "outcome": "send",
        "stage": "initial",
        "title": "Event detected",
        "body": "Vehicle event",
        "source": {"labels": ["car"]},
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as client:
        response = await client.post(
            "/webhook", json=payload, headers={"Idempotency-Key": "demo-key"}
        )
        assert response.status_code == 202
        assert response.json()["external_message_id"].startswith("demo-")
        assert response.headers["x-request-id"] == response.json()["external_message_id"]
        assert (await client.get("/health")).status_code == 200


async def test_demo_webhook_rejects_mismatched_idempotency_key() -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    payload = {
        "idempotency_key": "payload-key",
        "decision_id": "00000000-0000-0000-0000-000000000001",
        "observation_id": "00000000-0000-0000-0000-000000000002",
        "outcome": "send",
        "stage": "initial",
        "title": "Event detected",
        "body": "Vehicle event",
        "source": {},
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as client:
        response = await client.post(
            "/webhook", json=payload, headers={"Idempotency-Key": "header-key"}
        )
        assert response.status_code == 400
