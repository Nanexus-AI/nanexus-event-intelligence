"""Frigate-specific integration boundary. No core module may import this package."""

from nanexus_event_intelligence.adapters.frigate.config import FrigateMqttConfig
from nanexus_event_intelligence.adapters.frigate.descriptor import describe_frigate

__all__ = ["FrigateMqttConfig", "describe_frigate"]
