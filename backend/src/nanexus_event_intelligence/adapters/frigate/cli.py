"""Command-line entry points for Frigate development tools."""

import argparse
import asyncio
import os
from pathlib import Path

from pydantic import SecretStr

from nanexus_event_intelligence.adapters.frigate.config import FrigateMqttConfig
from nanexus_event_intelligence.adapters.frigate.recorder import FrigateFixtureRecorder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record redacted Frigate MQTT fixtures")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--duration", type=float, default=300)
    parser.add_argument("--max-messages", type=int)
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    host = os.environ.get("FRIGATE_MQTT_HOST")
    if not host:
        raise SystemExit("FRIGATE_MQTT_HOST is required")
    config = FrigateMqttConfig(
        host=host,
        port=int(os.environ.get("FRIGATE_MQTT_PORT", "1883")),
        username=os.environ.get("FRIGATE_MQTT_USERNAME"),
        password=(
            SecretStr(os.environ["FRIGATE_MQTT_PASSWORD"])
            if os.environ.get("FRIGATE_MQTT_PASSWORD")
            else None
        ),
        topic_prefix=os.environ.get("FRIGATE_MQTT_TOPIC_PREFIX", "frigate"),
        tls=os.environ.get("FRIGATE_MQTT_TLS", "false").lower() in {"1", "true", "yes"},
    )
    count = await FrigateFixtureRecorder(config).record(
        args.output,
        source_version=args.source_version,
        duration_seconds=args.duration,
        max_messages=args.max_messages,
    )
    print(f"Recorded {count} redacted messages to {args.output}")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Recording stopped by user")


if __name__ == "__main__":
    main()
