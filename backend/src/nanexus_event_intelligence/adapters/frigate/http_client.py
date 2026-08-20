"""Authenticated, origin-pinned, read-only Frigate HTTP API client."""

import asyncio
import json
import ssl
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from nanexus_event_intelligence.adapters.frigate.http_config import FrigateHttpConfig
from nanexus_event_intelligence.adapters.frigate.http_models import (
    FrigateEvent,
    FrigateReview,
    MediaResponse,
)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
Sleeper = Callable[[float], Awaitable[None]]


class FrigateApiError(RuntimeError):
    """Base error that never includes credentials, response bodies, or arbitrary URLs."""


class FrigateAuthenticationError(FrigateApiError):
    pass


class FrigateNotFoundError(FrigateApiError):
    pass


class FrigateTransientError(FrigateApiError):
    pass


class FrigateProtocolError(FrigateApiError):
    pass


class FrigateResponseTooLargeError(FrigateApiError):
    pass


def _identifier(value: str, name: str) -> str:
    if not value or len(value) > 512:
        raise ValueError(f"{name} must contain 1 to 512 characters")
    return quote(value, safe="")


class FrigateHttpClient:
    def __init__(
        self,
        config: FrigateHttpConfig,
        *,
        client: httpx.AsyncClient | None = None,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self.config = config
        self._sleeper = sleeper
        self._owns_client = client is None
        self._logged_in = False
        if client is not None:
            self._client = client
        else:
            verify: ssl.SSLContext | bool = True
            if config.ca_bundle is not None:
                verify = ssl.create_default_context(cafile=str(config.ca_bundle))
            self._client = httpx.AsyncClient(
                base_url=config.origin,
                timeout=httpx.Timeout(config.timeout_seconds),
                verify=verify,
                follow_redirects=False,
            )

    async def __aenter__(self) -> "FrigateHttpClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_version(self) -> str:
        content, _headers = await self._request("/api/version", self.config.max_json_bytes)
        text = content.decode("utf-8").strip()
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = text
        if isinstance(decoded, str) and decoded:
            return decoded
        if isinstance(decoded, dict):
            version = decoded.get("version")
            if isinstance(version, str):
                return version
        raise FrigateProtocolError("invalid version response")

    async def get_event(self, event_id: str) -> FrigateEvent:
        data = await self._request_json(f"/api/events/{_identifier(event_id, 'event_id')}")
        try:
            return FrigateEvent.model_validate(data)
        except ValidationError:
            raise FrigateProtocolError("invalid event response") from None

    async def list_events(
        self,
        *,
        after: float | None = None,
        before: float | None = None,
        cameras: tuple[str, ...] = (),
        limit: int = 100,
    ) -> list[FrigateEvent]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        params: dict[str, str | int | float] = {"limit": limit, "include_thumbnails": 0}
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        if cameras:
            params["cameras"] = ",".join(cameras)
        data = await self._request_json("/api/events", params=params)
        if not isinstance(data, list):
            raise FrigateProtocolError("invalid events response")
        try:
            return [FrigateEvent.model_validate(item) for item in data]
        except ValidationError:
            raise FrigateProtocolError("invalid events response") from None

    async def get_review(self, review_id: str) -> FrigateReview:
        data = await self._request_json(f"/api/review/{_identifier(review_id, 'review_id')}")
        try:
            return FrigateReview.model_validate(data)
        except ValidationError:
            raise FrigateProtocolError("invalid review response") from None

    async def get_review_for_event(self, event_id: str) -> FrigateReview:
        data = await self._request_json(f"/api/review/event/{_identifier(event_id, 'event_id')}")
        try:
            return FrigateReview.model_validate(data)
        except ValidationError:
            raise FrigateProtocolError("invalid review response") from None

    async def get_event_snapshot(self, event_id: str) -> MediaResponse:
        content, headers = await self._request(
            f"/api/events/{_identifier(event_id, 'event_id')}/snapshot.jpg",
            self.config.max_media_bytes,
        )
        return MediaResponse(
            content=content,
            content_type=headers.get("content-type", "application/octet-stream"),
            frame_time=headers.get("x-frame-time"),
        )

    async def get_review_preview(self, review_id: str) -> MediaResponse:
        content, headers = await self._request(
            f"/api/review/{_identifier(review_id, 'review_id')}/preview",
            self.config.max_media_bytes,
        )
        return MediaResponse(
            content=content,
            content_type=headers.get("content-type", "application/octet-stream"),
        )

    async def _request_json(
        self, path: str, *, params: Mapping[str, str | int | float] | None = None
    ) -> Any:
        content, _headers = await self._request(path, self.config.max_json_bytes, params=params)
        try:
            return json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise FrigateProtocolError("invalid JSON response") from None

    async def _ensure_login(self) -> None:
        if self._logged_in or self.config.username is None:
            return
        try:
            response = await self._client.post(
                f"{self.config.origin}/api/login",
                json={
                    "user": self.config.username,
                    "password": (
                        self.config.password.get_secret_value() if self.config.password else ""
                    ),
                },
                headers={"Accept": "application/json"},
            )
        except httpx.RequestError:
            raise FrigateTransientError("Frigate login request failed") from None
        if response.status_code not in {200, 201}:
            raise FrigateAuthenticationError("Frigate login failed")
        self._logged_in = True

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.config.bearer_token is not None:
            headers["Authorization"] = f"Bearer {self.config.bearer_token.get_secret_value()}"
        if self.config.proxy_secret is not None:
            headers["X-Proxy-Secret"] = self.config.proxy_secret.get_secret_value()
        return headers

    async def _request(
        self,
        path: str,
        limit: int,
        *,
        params: Mapping[str, str | int | float] | None = None,
    ) -> tuple[bytes, httpx.Headers]:
        if not path.startswith("/api/") or "://" in path:
            raise ValueError("only fixed Frigate API paths are allowed")
        await self._ensure_login()
        for attempt in range(self.config.max_retries + 1):
            response: httpx.Response | None = None
            try:
                request = self._client.build_request(
                    "GET", f"{self.config.origin}{path}", params=params, headers=self._headers()
                )
                response = await self._client.send(request, stream=True, follow_redirects=False)
                if response.status_code in {401, 403}:
                    raise FrigateAuthenticationError("Frigate authentication failed")
                if response.status_code == 404:
                    raise FrigateNotFoundError("Frigate resource was not found")
                if 300 <= response.status_code < 400:
                    raise FrigateProtocolError("Frigate redirect was refused")
                if response.status_code in RETRYABLE_STATUS:
                    raise FrigateTransientError("Frigate API is temporarily unavailable")
                if response.status_code >= 400:
                    raise FrigateProtocolError("Frigate API returned an unexpected status")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > limit:
                        raise FrigateResponseTooLargeError(
                            "Frigate response exceeded configured limit"
                        )
                return bytes(content), response.headers
            except (httpx.TimeoutException, httpx.NetworkError, FrigateTransientError):
                if attempt >= self.config.max_retries:
                    break
                delay = min(0.25 * (2**attempt), 5.0)
                if response is not None and response.headers.get("retry-after"):
                    try:
                        delay = min(float(response.headers["retry-after"]), 30.0)
                    except ValueError:
                        pass
                await self._sleeper(delay)
            finally:
                if response is not None:
                    await response.aclose()
        raise FrigateTransientError("Frigate API request failed after retries") from None
