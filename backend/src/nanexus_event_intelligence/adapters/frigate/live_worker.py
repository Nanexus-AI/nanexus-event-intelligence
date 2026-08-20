"""Live Frigate MQTT ingest worker with commit-before-ack delivery."""

import asyncio
import hashlib
import json
import ssl
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import paho.mqtt as paho
import paho.mqtt.client as mqtt
import structlog
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nanexus_event_intelligence.adapters.frigate.config import FrigateMqttConfig
from nanexus_event_intelligence.adapters.frigate.pipeline import FrigateIngestPipeline
from nanexus_event_intelligence.adapters.frigate.replay import FixtureMessage
from nanexus_event_intelligence.persistence.models import SourceInstance
from nanexus_event_intelligence.persistence.repositories import SourceInstanceRepository

logger = structlog.get_logger(__name__)


class FrigateLiveIngestWorker:
    """Persist each QoS message transactionally before issuing the MQTT ACK."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: FrigateMqttConfig,
        *,
        source_name: str,
        source_version: str | None,
        ingest_timeout_seconds: float = 30,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._source_name = source_name
        self._source_version = source_version
        self._ingest_timeout_seconds = ingest_timeout_seconds
        self._loop: asyncio.AbstractEventLoop | None = None
        self._source_id: UUID | None = None

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._source_id = await self._ensure_source()
        reconnect_delay = self._config.reconnect_delay_seconds
        while True:
            client = self._create_client()
            try:
                await asyncio.to_thread(
                    client.connect,
                    self._config.host,
                    self._config.port,
                    self._config.keepalive,
                )
                reconnect_delay = self._config.reconnect_delay_seconds
                await asyncio.to_thread(client.loop_forever, retry_first_connection=True)
            except (OSError, paho.MQTTException) as error:
                logger.warning("frigate_mqtt_unavailable", error_type=type(error).__name__)
            finally:
                client.disconnect()
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, self._config.reconnect_max_seconds)

    def _create_client(self) -> mqtt.Client:
        client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=self._config.client_id,
            clean_session=False,
            protocol=mqtt.MQTTv311,
            manual_ack=True,
        )
        if self._config.username is not None:
            password = self._config.password.get_secret_value() if self._config.password else None
            client.username_pw_set(self._config.username, password)
        if self._config.tls:
            client.tls_set_context(ssl.create_default_context())
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.reconnect_delay_set(
            min_delay=int(self._config.reconnect_delay_seconds),
            max_delay=int(self._config.reconnect_max_seconds),
        )
        return client

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        del userdata, flags, properties
        if reason_code.is_failure:
            logger.warning("frigate_mqtt_connect_failed", reason_code=str(reason_code))
            return
        for topic in self._config.recording_topics:
            client.subscribe(topic, qos=1)
        logger.info("frigate_mqtt_connected", topics=len(self._config.recording_topics))

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        del userdata
        if self._loop is None or self._source_id is None:
            client.disconnect()
            return
        future = asyncio.run_coroutine_threadsafe(self._ingest(message), self._loop)
        try:
            future.result(timeout=self._ingest_timeout_seconds)
        except Exception as error:
            future.cancel()
            logger.warning("frigate_mqtt_ingest_deferred", error_type=type(error).__name__)
            client.disconnect()
            return
        result = client.ack(message.mid, message.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("frigate_mqtt_ack_failed", result=int(result))
            client.disconnect()

    async def _ensure_source(self) -> UUID:
        async with self._session_factory.begin() as session:
            repository = SourceInstanceRepository(session)
            source = await repository.get_by_type_and_name("frigate", self._source_name)
            if source is None:
                source = await repository.add(
                    SourceInstance(
                        source_type="frigate",
                        name=self._source_name,
                        source_version=self._source_version,
                        adapter_version="0.3.0",
                        capabilities={
                            "live_events": True,
                            "historical_query": True,
                            "media_fetch": True,
                        },
                        health_status="starting",
                    )
                )
            return source.id

    async def _ingest(self, message: mqtt.MQTTMessage) -> None:
        observed_at = datetime.now(UTC)
        payload_bytes = bytes(message.payload)
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        try:
            payload = json.loads(payload_bytes)
            if not isinstance(payload, dict):
                raise ValueError("MQTT payload must be an object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            payload = {"_invalid_payload_sha256": payload_hash}
        fixture_message = FixtureMessage(
            topic=str(message.topic),
            observed_at=observed_at,
            qos=int(message.qos),
            retain=message.retain,
            payload_sha256=payload_hash,
            payload=payload,
        )
        cursor = f"mqtt-mid:{message.mid}:{observed_at.isoformat()}"
        source_id = self._source_id
        if source_id is None:
            raise RuntimeError("source is not initialized")
        async with self._session_factory.begin() as session:
            await FrigateIngestPipeline(session, source_instance_id=source_id).ingest(
                fixture_message,
                stream=f"mqtt:{message.topic}",
                cursor=cursor,
            )
