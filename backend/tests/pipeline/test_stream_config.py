import pytest
from pydantic import ValidationError

from nanexus_event_intelligence.pipeline.config import RedisStreamConfig


def test_stream_config_has_safe_bounded_defaults() -> None:
    config = RedisStreamConfig()
    assert config.max_delivery_attempts == 5
    assert config.max_inflight_messages == 100_000
    assert config.dlq_stream.endswith(":dlq")


@pytest.mark.parametrize("name", ["bad name", "../stream", "", "x" * 129])
def test_stream_config_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ValidationError):
        RedisStreamConfig(stream=name)
