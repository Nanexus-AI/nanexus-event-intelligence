import pytest
from pydantic import ValidationError

from nanexus_event_intelligence.adapters.frigate.config import FrigateMqttConfig
from nanexus_event_intelligence.adapters.frigate.descriptor import describe_frigate


def test_recording_topics_are_read_only_and_scoped() -> None:
    config = FrigateMqttConfig(host="mqtt.local", topic_prefix="site/frigate/")
    assert config.recording_topics == (
        "site/frigate/reviews",
        "site/frigate/events",
        "site/frigate/tracked_object_update",
        "site/frigate/available",
    )
    assert all(not topic.endswith("/set") for topic in config.recording_topics)


def test_wildcard_topic_prefix_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FrigateMqttConfig(host="mqtt.local", topic_prefix="frigate/#")


def test_descriptor_declares_no_writeback() -> None:
    descriptor = describe_frigate("0.17.1-416a9b7")
    assert descriptor.source_type == "frigate"
    assert descriptor.source_version == "0.17.1-416a9b7"
    assert descriptor.capabilities.live_events
    assert descriptor.capabilities.review_groups
    assert descriptor.capabilities.historical_query
    assert descriptor.capabilities.media_fetch
    assert not descriptor.capabilities.writeback
