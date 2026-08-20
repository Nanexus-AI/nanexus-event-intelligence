"""Minimal no-network plugin proving the public lifecycle contract."""

from collections.abc import Mapping
from typing import Any

from nanexus_event_intelligence.core.plugin import (
    PLUGIN_CONTRACT_VERSION,
    PluginContext,
    PluginHealth,
    PluginKind,
    PluginManifest,
    PluginPermission,
    PluginState,
)
from nanexus_event_intelligence.core.source_adapter import ValidationReport


class _HeartbeatHandle:
    def __init__(self, plugin: "HeartbeatPlugin") -> None:
        self._plugin = plugin

    async def stop(self) -> None:
        self._plugin._state = PluginState.STOPPED


class HeartbeatPlugin:
    """Example only: records lifecycle without business or external side effects."""

    def __init__(self) -> None:
        self._state = PluginState.REGISTERED

    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id="community.example.heartbeat",
            name="Community heartbeat example",
            plugin_version="0.1.0",
            contract_version=PLUGIN_CONTRACT_VERSION,
            minimum_platform_version="0.1.0",
            kind=PluginKind.POLICY_PACK,
            capabilities=("lifecycle_probe",),
            config_schema={
                "type": "object",
                "properties": {"enabled": {"type": "boolean"}},
                "additionalProperties": False,
            },
            permissions=PluginPermission(),
        )

    def validate_config(self, config: Mapping[str, Any]) -> ValidationReport:
        unknown = sorted(set(config) - {"enabled"})
        if unknown:
            return ValidationReport(valid=False, errors=[f"unknown keys: {', '.join(unknown)}"])
        enabled = config.get("enabled", True)
        if not isinstance(enabled, bool):
            return ValidationReport(valid=False, errors=["enabled must be a boolean"])
        return ValidationReport(valid=True)

    async def start(self, context: PluginContext, config: Mapping[str, Any]) -> _HeartbeatHandle:
        del context
        self._state = PluginState.HEALTHY if config.get("enabled", True) else PluginState.DEGRADED
        return _HeartbeatHandle(self)

    def health(self) -> PluginHealth:
        return PluginHealth(state=self._state)
