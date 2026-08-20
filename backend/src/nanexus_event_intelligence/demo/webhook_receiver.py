import hashlib

import structlog
from fastapi import FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from nanexus_event_intelligence.notifications.models import NotificationMessage

logger = structlog.get_logger(__name__)
app = FastAPI(title="Nanexus Community Demo Webhook", version="1.0.0")


class HealthResponse(BaseModel):
    status: str = "ok"


class AcceptedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str = "accepted"
    external_message_id: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/webhook", response_model=AcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def webhook(
    message: NotificationMessage,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=512),
) -> AcceptedResponse:
    if idempotency_key != message.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency key mismatch")
    external_id = f"demo-{hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]}"
    response.headers["X-Request-ID"] = external_id
    logger.info(
        "community_demo_notification_received",
        external_message_id=external_id,
        outcome=message.outcome,
        stage=message.stage,
    )
    return AcceptedResponse(external_message_id=external_id)
