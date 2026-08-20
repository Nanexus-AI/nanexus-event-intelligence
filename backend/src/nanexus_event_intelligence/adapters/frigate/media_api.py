from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nanexus_event_intelligence.adapters.frigate.http_client import (
    FrigateApiError,
    FrigateHttpClient,
    FrigateNotFoundError,
    FrigateTransientError,
)
from nanexus_event_intelligence.adapters.frigate.http_config import FrigateHttpConfig
from nanexus_event_intelligence.adapters.frigate.http_models import MediaResponse
from nanexus_event_intelligence.config import Settings
from nanexus_event_intelligence.persistence.models import Observation, SourceInstance

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class MediaClient(Protocol):
    async def __aenter__(self) -> "MediaClient": ...
    async def __aexit__(self, *_args: object) -> None: ...
    async def get_event_snapshot(self, event_id: str) -> MediaResponse: ...


MediaClientFactory = Callable[[FrigateHttpConfig], MediaClient]


def _secret(value: SecretStr | None) -> SecretStr | None:
    if value is None:
        return None
    return value if value.get_secret_value() else None


def _config(settings: Settings) -> FrigateHttpConfig:
    if not settings.frigate_http_base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Frigate media access is not configured",
        )
    try:
        return FrigateHttpConfig(
            base_url=settings.frigate_http_base_url,
            bearer_token=_secret(settings.frigate_http_bearer_token),
            username=settings.frigate_http_username or None,
            password=_secret(settings.frigate_http_password),
            proxy_secret=_secret(settings.frigate_http_proxy_secret),
            trusted_internal=settings.frigate_http_trusted_internal,
            ca_bundle=Path(settings.frigate_http_ca_bundle)
            if settings.frigate_http_ca_bundle
            else None,
        )
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Frigate media configuration is invalid",
        ) from None


def _event_id(observation: Observation) -> str | None:
    if observation.source_namespace == "frigate.event":
        return observation.source_entity_id
    if observation.source_namespace != "frigate.review":
        return None
    links = observation.extensions.get("links", [])
    if not isinstance(links, list):
        return None
    for value in links:
        if (
            isinstance(value, dict)
            and value.get("namespace") == "frigate.event"
            and isinstance(value.get("source_entity_id"), str)
        ):
            return cast(str, value["source_entity_id"])
    return None


def create_frigate_media_router(
    settings: Settings,
    *,
    client_factory: MediaClientFactory = FrigateHttpClient,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/events", tags=["event-media"])

    @router.get("/{observation_id}/media/snapshot")
    async def snapshot(observation_id: UUID, request: Request) -> Response:
        factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
        async with factory() as session:
            row = (
                await session.execute(
                    select(Observation, SourceInstance)
                    .join(SourceInstance, SourceInstance.id == Observation.source_instance_id)
                    .where(Observation.id == observation_id)
                )
            ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="event not found")
        observation, source = row
        if source.source_type != "frigate":
            raise HTTPException(status_code=404, detail="snapshot is not supported")
        event_id = _event_id(observation)
        if event_id is None:
            raise HTTPException(status_code=404, detail="snapshot is not associated")
        try:
            async with client_factory(_config(settings)) as client:
                media = await client.get_event_snapshot(event_id)
        except FrigateNotFoundError:
            raise HTTPException(status_code=404, detail="snapshot was not found") from None
        except FrigateTransientError:
            raise HTTPException(
                status_code=503, detail="Frigate media is temporarily unavailable"
            ) from None
        except FrigateApiError:
            raise HTTPException(status_code=502, detail="Frigate media request failed") from None
        content_type = media.content_type.split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=502, detail="Frigate returned an unsupported media type"
            )
        return Response(
            content=media.content,
            media_type=content_type,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    return router
