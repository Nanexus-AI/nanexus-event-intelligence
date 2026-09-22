"""Frigate implementation of the source-neutral evidence content port."""

from typing import cast

from nanexus_event_intelligence.adapters.frigate.http_client import (
    FrigateApiError,
    FrigateHttpClient,
    FrigateNotFoundError,
    FrigateTransientError,
)
from nanexus_event_intelligence.adapters.frigate.media_api import ALLOWED_IMAGE_TYPES, _config
from nanexus_event_intelligence.config import Settings
from nanexus_event_intelligence.core.evidence import (
    EvidenceContent,
    EvidenceContentRequest,
    EvidenceContentUnavailable,
)


def _event_id(request: EvidenceContentRequest) -> str | None:
    if request.source_namespace == "frigate.event":
        return request.source_entity_id
    if request.source_namespace != "frigate.review":
        return None
    links = request.extensions.get("links", [])
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


class FrigateEvidenceContentReader:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def read(self, request: EvidenceContentRequest) -> EvidenceContent:
        if request.source_type != "frigate":
            raise EvidenceContentUnavailable("unsupported_source")
        event_id = _event_id(request)
        if event_id is None:
            raise EvidenceContentUnavailable("source_unavailable")
        try:
            async with FrigateHttpClient(_config(self._settings)) as client:
                media = await client.get_event_snapshot(event_id)
        except FrigateNotFoundError as error:
            raise EvidenceContentUnavailable("not_found") from error
        except FrigateTransientError as error:
            raise EvidenceContentUnavailable("temporarily_unavailable", retryable=True) from error
        except FrigateApiError as error:
            raise EvidenceContentUnavailable("upstream_failed") from error
        content_type = media.content_type.split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_TYPES or len(media.content) > 10 * 1024 * 1024:
            raise EvidenceContentUnavailable("media_limits")
        return EvidenceContent(content=media.content, content_type=content_type)
