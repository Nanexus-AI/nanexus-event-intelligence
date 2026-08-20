"""Frigate capability declaration."""

from nanexus_event_intelligence.core.source_adapter import CapabilitySet, SourceDescriptor

ADAPTER_VERSION = "0.1.0"


def describe_frigate(source_version: str | None = None) -> SourceDescriptor:
    return SourceDescriptor(
        source_type="frigate",
        source_version=source_version,
        adapter_version=ADAPTER_VERSION,
        capabilities=CapabilitySet(
            live_events=True,
            historical_query=True,
            media_fetch=True,
            object_tracks=True,
            review_groups=True,
            semantic_metadata=True,
            health=True,
            writeback=False,
        ),
    )
