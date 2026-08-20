"""Entrypoint for the live Frigate MQTT ingest worker."""

import asyncio

from nanexus_event_intelligence.adapters.frigate.config import FrigateMqttConfig
from nanexus_event_intelligence.adapters.frigate.live_worker import FrigateLiveIngestWorker
from nanexus_event_intelligence.config import get_settings
from nanexus_event_intelligence.persistence.database import create_engine, create_session_factory


async def run() -> None:
    settings = get_settings()
    if not settings.frigate_mqtt_host:
        raise SystemExit("FRIGATE_MQTT_HOST is required")
    engine = create_engine(settings.database_url)
    config = FrigateMqttConfig(
        host=settings.frigate_mqtt_host,
        port=settings.frigate_mqtt_port,
        username=settings.frigate_mqtt_username or None,
        password=settings.frigate_mqtt_password,
        topic_prefix=settings.frigate_mqtt_topic_prefix,
        client_id=settings.frigate_mqtt_client_id,
        tls=settings.frigate_mqtt_tls,
    )
    try:
        await FrigateLiveIngestWorker(
            create_session_factory(engine),
            config,
            source_name=settings.frigate_source_name,
            source_version=settings.frigate_source_version or None,
            ingest_timeout_seconds=settings.frigate_mqtt_ingest_timeout_seconds,
        ).run()
    finally:
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
