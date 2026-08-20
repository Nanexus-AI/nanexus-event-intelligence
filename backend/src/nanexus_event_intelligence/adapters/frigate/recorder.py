"""Read-only Frigate MQTT fixture recorder with bounded reconnect backoff."""

import asyncio
import contextlib
import ssl
from datetime import UTC, datetime
from pathlib import Path

import aiomqtt

from nanexus_event_intelligence.adapters.frigate.config import FrigateMqttConfig
from nanexus_event_intelligence.adapters.frigate.fixtures import FixtureBundleWriter


class FrigateFixtureRecorder:
    def __init__(self, config: FrigateMqttConfig) -> None:
        self.config = config

    async def record(
        self,
        output_dir: Path,
        *,
        source_version: str,
        max_messages: int | None = None,
        duration_seconds: float | None = None,
    ) -> int:
        if max_messages is not None and max_messages < 1:
            raise ValueError("max_messages must be positive")
        if duration_seconds is not None and duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")

        loop = asyncio.get_running_loop()
        timeout_at = loop.time() + duration_seconds if duration_seconds is not None else None
        reconnect_delay = self.config.reconnect_delay_seconds
        with FixtureBundleWriter(output_dir, source_version=source_version) as writer:
            while max_messages is None or writer.message_count < max_messages:
                if timeout_at is not None and loop.time() >= timeout_at:
                    break
                try:
                    await self._record_connection(writer, max_messages, timeout_at)
                    reconnect_delay = self.config.reconnect_delay_seconds
                except aiomqtt.MqttError:
                    if timeout_at is not None:
                        remaining = timeout_at - loop.time()
                        if remaining <= 0:
                            break
                        await asyncio.sleep(min(reconnect_delay, remaining))
                    else:
                        await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, self.config.reconnect_max_seconds)
            return writer.message_count

    async def _record_connection(
        self,
        writer: FixtureBundleWriter,
        max_messages: int | None,
        timeout_at: float | None,
    ) -> None:
        tls_context = ssl.create_default_context() if self.config.tls else None
        password = self.config.password.get_secret_value() if self.config.password else None
        async with aiomqtt.Client(
            hostname=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=password,
            identifier=self.config.client_id,
            keepalive=self.config.keepalive,
            tls_context=tls_context,
        ) as client:
            for topic in self.config.recording_topics:
                await client.subscribe(topic, qos=1)

            while max_messages is None or writer.message_count < max_messages:
                timeout = None
                if timeout_at is not None:
                    timeout = timeout_at - asyncio.get_running_loop().time()
                    if timeout <= 0:
                        return
                try:
                    async with asyncio.timeout(timeout):
                        message = await anext(client.messages)
                except TimeoutError:
                    return
                with contextlib.suppress(UnicodeDecodeError, ValueError):
                    writer.write(
                        topic=str(message.topic),
                        payload_bytes=bytes(message.payload),
                        observed_at=datetime.now(UTC),
                        qos=int(message.qos),
                        retain=message.retain,
                    )
