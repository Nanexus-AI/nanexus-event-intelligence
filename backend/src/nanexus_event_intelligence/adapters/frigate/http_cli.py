"""Safe, read-only Frigate HTTP connectivity smoke test."""

import asyncio
import os
from pathlib import Path

from pydantic import SecretStr

from nanexus_event_intelligence.adapters.frigate.http_client import (
    FrigateApiError,
    FrigateHttpClient,
    FrigateNotFoundError,
)
from nanexus_event_intelligence.adapters.frigate.http_config import FrigateHttpConfig


def optional_secret(name: str) -> SecretStr | None:
    value = os.environ.get(name)
    return SecretStr(value) if value else None


async def async_main() -> None:
    base_url = os.environ.get("FRIGATE_HTTP_BASE_URL")
    if not base_url:
        raise SystemExit("FRIGATE_HTTP_BASE_URL is required")
    username = os.environ.get("FRIGATE_HTTP_USERNAME") or None
    config = FrigateHttpConfig(
        base_url=base_url,
        bearer_token=optional_secret("FRIGATE_HTTP_BEARER_TOKEN"),
        username=username,
        password=optional_secret("FRIGATE_HTTP_PASSWORD"),
        proxy_secret=optional_secret("FRIGATE_HTTP_PROXY_SECRET"),
        trusted_internal=os.environ.get("FRIGATE_HTTP_TRUSTED_INTERNAL", "false").lower()
        in {"1", "true", "yes"},
        ca_bundle=(
            Path(os.environ["FRIGATE_HTTP_CA_BUNDLE"])
            if os.environ.get("FRIGATE_HTTP_CA_BUNDLE")
            else None
        ),
    )
    async with FrigateHttpClient(config) as client:
        version = await client.get_version()
        events = await client.list_events(limit=20)
        checks = ["version", "events"]
        media_bytes = 0
        for candidate in events:
            try:
                event = await client.get_event(candidate.id)
                if "event" not in checks:
                    checks.append("event")
            except FrigateNotFoundError:
                continue
            if event.has_snapshot and "snapshot" not in checks:
                try:
                    snapshot = await client.get_event_snapshot(event.id)
                    media_bytes += len(snapshot.content)
                    checks.append("snapshot")
                except FrigateNotFoundError:
                    pass
            try:
                review = await client.get_review_for_event(event.id)
                if "review_from_event" not in checks:
                    checks.append("review_from_event")
                await client.get_review(review.id)
                if "review" not in checks:
                    checks.append("review")
                if "review_preview" not in checks:
                    preview = await client.get_review_preview(review.id)
                    media_bytes += len(preview.content)
                    checks.append("review_preview")
            except FrigateNotFoundError:
                pass
            if all(
                item in checks
                for item in ("event", "review_from_event", "review", "snapshot", "review_preview")
            ):
                break
    print(
        "Frigate HTTP read-only smoke test passed: "
        f"version={version}, checks={','.join(checks)}, media_bytes={media_bytes}"
    )


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Frigate HTTP smoke test stopped by user")
    except FrigateApiError as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
