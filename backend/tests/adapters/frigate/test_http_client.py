from collections.abc import Awaitable, Callable

import httpx
import pytest
from pydantic import SecretStr

from nanexus_event_intelligence.adapters.frigate.http_client import (
    FrigateAuthenticationError,
    FrigateHttpClient,
    FrigateNotFoundError,
    FrigateProtocolError,
    FrigateResponseTooLargeError,
    FrigateTransientError,
)
from nanexus_event_intelligence.adapters.frigate.http_config import FrigateHttpConfig

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def config(**kwargs: object) -> FrigateHttpConfig:
    return FrigateHttpConfig(base_url="https://frigate.local:8971", **kwargs)


def client_for(
    handler: Handler, cfg: FrigateHttpConfig | None = None, **kwargs: object
) -> FrigateHttpClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(
        base_url="https://frigate.local:8971", transport=transport, follow_redirects=False
    )
    return FrigateHttpClient(cfg or config(), client=http, **kwargs)


@pytest.mark.asyncio
async def test_version_and_bearer_authentication() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        assert request.headers["authorization"] == "Bearer test-token"
        return httpx.Response(200, json="0.17.1-416a9b7")

    api = client_for(handler, config(bearer_token=SecretStr("test-token")))
    assert await api.get_version() == "0.17.1-416a9b7"


@pytest.mark.asyncio
async def test_event_review_listing_and_media_methods() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/api/events":
            assert request.url.params["include_thumbnails"] == "0"
            assert request.url.params["cameras"] == "camera_1"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "event-1",
                        "label": "car",
                        "camera": "camera_1",
                        "start_time": 1,
                        "end_time": 2,
                        "zones": [],
                        "has_clip": True,
                        "has_snapshot": True,
                    }
                ],
            )
        if request.url.path == "/api/events/event-1":
            return httpx.Response(
                200,
                json={
                    "id": "event-1",
                    "label": "car",
                    "camera": "camera_1",
                    "start_time": 1,
                    "zones": [],
                    "has_clip": True,
                    "has_snapshot": True,
                },
            )
        if request.url.path in {"/api/review/review-1", "/api/review/event/event-1"}:
            return httpx.Response(
                200,
                json={
                    "id": "review-1",
                    "camera": "camera_1",
                    "start_time": 1,
                    "severity": "alert",
                    "data": {},
                },
            )
        if request.url.path.endswith("snapshot.jpg"):
            return httpx.Response(
                200, content=b"jpeg", headers={"content-type": "image/jpeg", "x-frame-time": "1.5"}
            )
        if request.url.path.endswith("/preview"):
            return httpx.Response(200, content=b"preview", headers={"content-type": "video/mp4"})
        return httpx.Response(404)

    api = client_for(handler)
    events = await api.list_events(cameras=("camera_1",), after=1, before=3)
    event = await api.get_event("event-1")
    review = await api.get_review("review-1")
    from_event = await api.get_review_for_event("event-1")
    snapshot = await api.get_event_snapshot("event-1")
    preview = await api.get_review_preview("review-1")

    assert events[0].id == event.id == "event-1"
    assert review.id == from_event.id == "review-1"
    assert snapshot.content == b"jpeg" and snapshot.frame_time == "1.5"
    assert preview.content_type == "video/mp4"
    assert len(seen) == 6


@pytest.mark.asyncio
async def test_username_login_uses_cookie_without_exposing_password() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/login":
            assert request.method == "POST"
            assert request.content == b'{"user":"viewer","password":"private-password"}'
            return httpx.Response(200, headers={"set-cookie": "access_token=signed; Path=/"})
        assert request.headers["cookie"] == "access_token=signed"
        return httpx.Response(200, content="0.17.1")

    api = client_for(
        handler,
        config(username="viewer", password=SecretStr("private-password")),
    )
    assert await api.get_version() == "0.17.1"
    assert await api.get_version() == "0.17.1"
    assert [request.url.path for request in requests].count("/api/login") == 1


@pytest.mark.asyncio
async def test_proxy_secret_header() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-proxy-secret"] == "proxy-secret"
        return httpx.Response(200, content="0.17.1")

    api = client_for(handler, config(proxy_secret=SecretStr("proxy-secret")))
    assert await api.get_version() == "0.17.1"


@pytest.mark.asyncio
async def test_retry_uses_retry_after_then_succeeds() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, headers={"retry-after": "0.1"})
        return httpx.Response(200, content="0.17.1")

    async def sleeper(delay: float) -> None:
        sleeps.append(delay)

    api = client_for(handler, config(max_retries=2), sleeper=sleeper)
    assert await api.get_version() == "0.17.1"
    assert attempts == 2 and sleeps == [0.1]


@pytest.mark.asyncio
async def test_network_failure_is_sanitized_after_retries() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret-host-detail", request=request)

    async def sleeper(_delay: float) -> None:
        return None

    api = client_for(handler, config(max_retries=1), sleeper=sleeper)
    with pytest.raises(FrigateTransientError) as error:
        await api.get_version()
    assert "secret-host-detail" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, FrigateAuthenticationError),
        (403, FrigateAuthenticationError),
        (404, FrigateNotFoundError),
        (302, FrigateProtocolError),
        (422, FrigateProtocolError),
    ],
)
async def test_status_errors_are_typed_and_redirects_are_refused(
    status: int, error_type: type[Exception]
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"location": "http://attacker.invalid/secret"})

    api = client_for(handler)
    with pytest.raises(error_type) as error:
        await api.get_event("missing")
    assert "attacker" not in str(error.value)


@pytest.mark.asyncio
async def test_response_size_limit_is_enforced() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2048)

    api = client_for(handler, config(max_json_bytes=1024))
    with pytest.raises(FrigateResponseTooLargeError):
        await api.get_version()


@pytest.mark.asyncio
async def test_ids_cannot_escape_fixed_api_path() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == b"/api/events/..%2Fversion"
        return httpx.Response(404)

    api = client_for(handler)
    with pytest.raises(FrigateNotFoundError):
        await api.get_event("../version")


@pytest.mark.asyncio
async def test_login_network_error_is_sanitized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("login-secret-detail", request=request)

    api = client_for(handler, config(username="viewer", password=SecretStr("private-password")))
    with pytest.raises(FrigateTransientError) as error:
        await api.get_version()
    assert "login-secret-detail" not in str(error.value)
    assert error.value.__cause__ is None
