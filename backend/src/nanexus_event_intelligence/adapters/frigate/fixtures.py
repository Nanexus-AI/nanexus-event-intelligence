"""Portable JSONL fixture bundle writer."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from nanexus_event_intelligence.adapters.frigate.redaction import redact


@dataclass(frozen=True, slots=True)
class RecordedMessage:
    topic: str
    observed_at: str
    qos: int
    retain: bool
    payload_sha256: str
    payload: Any


class FixtureBundleWriter:
    def __init__(self, output_dir: Path, *, source_version: str) -> None:
        self.output_dir = output_dir
        self.source_version = source_version
        self._stream: TextIO | None = None
        self.message_count = 0

    def __enter__(self) -> "FixtureBundleWriter":
        self.output_dir.mkdir(parents=True, exist_ok=False)
        metadata = {
            "bundle_schema_version": "1.0",
            "source_type": "frigate",
            "source_version": self.source_version,
            "created_at": datetime.now(UTC).isoformat(),
            "contains_secrets": False,
        }
        (self.output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._stream = (self.output_dir / "messages.jsonl").open("x", encoding="utf-8")
        return self

    def __exit__(self, *_args: object) -> None:
        if self._stream is not None:
            self._stream.close()

    def write(
        self,
        *,
        topic: str,
        payload_bytes: bytes,
        observed_at: datetime,
        qos: int,
        retain: bool,
    ) -> RecordedMessage:
        if self._stream is None:
            raise RuntimeError("fixture bundle writer is not open")
        decoded = json.loads(payload_bytes)
        safe_payload = redact(decoded)
        canonical = json.dumps(safe_payload, separators=(",", ":"), sort_keys=True).encode()
        message = RecordedMessage(
            topic=topic,
            observed_at=observed_at.astimezone(UTC).isoformat(),
            qos=qos,
            retain=retain,
            payload_sha256=hashlib.sha256(canonical).hexdigest(),
            payload=safe_payload,
        )
        self._stream.write(
            json.dumps(asdict(message), separators=(",", ":"), sort_keys=True) + "\n"
        )
        self._stream.flush()
        self.message_count += 1
        return message
