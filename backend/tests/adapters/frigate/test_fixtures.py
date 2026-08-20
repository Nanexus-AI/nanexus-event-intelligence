import json
from datetime import UTC, datetime

import pytest

from nanexus_event_intelligence.adapters.frigate.fixtures import FixtureBundleWriter
from nanexus_event_intelligence.adapters.frigate.redaction import REDACTED, redact


def test_redaction_is_recursive_and_removes_url_credentials() -> None:
    payload = {
        "password": "secret",
        "nested": [{"token": "abc", "url": "rtsp://alice:hunter2@camera/stream"}],
        "camera": "front",
    }
    assert redact(payload) == {
        "password": REDACTED,
        "nested": [{"token": REDACTED, "url": "rtsp://[REDACTED]@camera/stream"}],
        "camera": "front",
    }


def test_bundle_contains_only_redacted_jsonl(tmp_path) -> None:
    output = tmp_path / "bundle"
    with FixtureBundleWriter(output, source_version="0.17.1-test") as writer:
        message = writer.write(
            topic="frigate/reviews",
            payload_bytes=json.dumps({"type": "new", "password": "secret"}).encode(),
            observed_at=datetime(2026, 8, 17, tzinfo=UTC),
            qos=1,
            retain=False,
        )
    metadata = json.loads((output / "metadata.json").read_text())
    line = json.loads((output / "messages.jsonl").read_text())
    assert metadata["contains_secrets"] is False
    assert line["payload"]["password"] == REDACTED
    assert "secret" not in (output / "messages.jsonl").read_text()
    assert len(message.payload_sha256) == 64


def test_bundle_refuses_to_overwrite_existing_capture(tmp_path) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    with pytest.raises(FileExistsError), FixtureBundleWriter(output, source_version="0.17.1"):
        pass
