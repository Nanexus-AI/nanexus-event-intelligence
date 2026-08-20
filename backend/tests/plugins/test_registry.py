from collections.abc import Mapping
from typing import Any

import pytest

from nanexus_event_intelligence.core.plugin import (
    PLUGIN_CONTRACT_VERSION,
    PluginContext,
    PluginHealth,
    PluginKind,
    PluginManifest,
    PluginState,
)
from nanexus_event_intelligence.core.source_adapter import ValidationReport
from nanexus_event_intelligence.plugins import (
    PluginCompatibilityError,
    PluginRegistrationError,
    PluginRegistry,
)
from nanexus_event_intelligence.plugins.examples.heartbeat import HeartbeatPlugin


@pytest.mark.asyncio
async def test_example_plugin_lifecycle() -> None:
    registry = PluginRegistry(platform_version="0.1.0")
    registry.register(HeartbeatPlugin(), {"enabled": True})

    assert registry.manifests[0].plugin_id == "community.example.heartbeat"
    assert (await registry.start_all(PluginContext()))[
        "community.example.heartbeat"
    ].state is PluginState.HEALTHY
    assert (await registry.stop_all())["community.example.heartbeat"].state is PluginState.STOPPED


def test_registration_rejects_invalid_config_and_duplicate_id() -> None:
    registry = PluginRegistry(platform_version="0.1.0")
    with pytest.raises(PluginRegistrationError, match="unknown keys"):
        registry.register(HeartbeatPlugin(), {"surprise": True})

    registry.register(HeartbeatPlugin(), {})
    with pytest.raises(PluginRegistrationError, match="duplicate plugin_id"):
        registry.register(HeartbeatPlugin(), {})


def test_registration_rejects_contract_and_platform_incompatibility() -> None:
    plugin = _ConfigurablePlugin(contract_version="2.0.0")
    with pytest.raises(PluginCompatibilityError, match="requires contract"):
        PluginRegistry(platform_version="0.1.0").register(plugin, {})

    plugin = _ConfigurablePlugin(minimum_platform_version="0.2.0")
    with pytest.raises(PluginCompatibilityError, match="requires platform"):
        PluginRegistry(platform_version="0.1.0").register(plugin, {})


@pytest.mark.asyncio
async def test_start_and_stop_failures_are_isolated() -> None:
    registry = PluginRegistry(platform_version="0.1.0")
    registry.register(_ConfigurablePlugin(plugin_id="test.fail", fail_start=True), {})
    registry.register(_ConfigurablePlugin(plugin_id="test.healthy"), {})

    health = await registry.start_all(PluginContext())

    assert health["test.fail"].state is PluginState.FAILED
    assert "start failed" in (health["test.fail"].message or "")
    assert health["test.healthy"].state is PluginState.HEALTHY

    registry = PluginRegistry(platform_version="0.1.0")
    registry.register(_ConfigurablePlugin(plugin_id="test.stop", fail_stop=True), {})
    registry.register(_ConfigurablePlugin(plugin_id="test.stop-ok"), {})
    await registry.start_all(PluginContext())

    health = await registry.stop_all()

    assert health["test.stop"].state is PluginState.FAILED
    assert health["test.stop-ok"].state is PluginState.STOPPED


class _Handle:
    def __init__(self, *, fail_stop: bool) -> None:
        self._fail_stop = fail_stop

    async def stop(self) -> None:
        if self._fail_stop:
            raise RuntimeError("stop failed")


class _ConfigurablePlugin:
    def __init__(
        self,
        *,
        plugin_id: str = "test.plugin",
        contract_version: str = PLUGIN_CONTRACT_VERSION,
        minimum_platform_version: str = "0.1.0",
        fail_start: bool = False,
        fail_stop: bool = False,
    ) -> None:
        self._manifest = PluginManifest(
            plugin_id=plugin_id,
            name="Test plugin",
            plugin_version="1.0.0",
            contract_version=contract_version,
            minimum_platform_version=minimum_platform_version,
            kind=PluginKind.POLICY_PACK,
        )
        self._fail_start = fail_start
        self._fail_stop = fail_stop

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    def validate_config(self, config: Mapping[str, Any]) -> ValidationReport:
        del config
        return ValidationReport(valid=True)

    async def start(self, context: PluginContext, config: Mapping[str, Any]) -> _Handle:
        del context, config
        if self._fail_start:
            raise RuntimeError("start failed")
        return _Handle(fail_stop=self._fail_stop)

    def health(self) -> PluginHealth:
        return PluginHealth(state=PluginState.HEALTHY)
