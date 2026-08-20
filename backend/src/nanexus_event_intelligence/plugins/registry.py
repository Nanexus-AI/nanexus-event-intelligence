"""Explicit registry for trusted Community and Pro plugins."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from nanexus_event_intelligence.core.plugin import (
    PLUGIN_CONTRACT_VERSION,
    CommunityPlugin,
    PluginContext,
    PluginHandle,
    PluginHealth,
    PluginManifest,
    PluginState,
)


class PluginRegistrationError(ValueError):
    pass


class PluginCompatibilityError(PluginRegistrationError):
    pass


@dataclass
class RegisteredPlugin:
    plugin: CommunityPlugin
    config: Mapping[str, Any]
    handle: PluginHandle | None = None
    runtime_health: PluginHealth = PluginHealth(state=PluginState.REGISTERED)


class PluginRegistry:
    """Own plugin lifecycle without importing or scanning implementation packages."""

    def __init__(
        self,
        *,
        platform_version: str,
        contract_version: str = PLUGIN_CONTRACT_VERSION,
    ) -> None:
        self._platform_version = platform_version
        self._contract_version = contract_version
        self._plugins: dict[str, RegisteredPlugin] = {}

    @property
    def manifests(self) -> tuple[PluginManifest, ...]:
        return tuple(item.plugin.manifest for item in self._plugins.values())

    def register(self, plugin: CommunityPlugin, config: Mapping[str, Any]) -> None:
        manifest = plugin.manifest
        if manifest.plugin_id in self._plugins:
            raise PluginRegistrationError(f"duplicate plugin_id: {manifest.plugin_id}")
        if _major(manifest.contract_version) != _major(self._contract_version):
            raise PluginCompatibilityError(
                f"plugin {manifest.plugin_id} requires contract {manifest.contract_version}; "
                f"host provides {self._contract_version}"
            )
        if _version_tuple(manifest.minimum_platform_version) > _version_tuple(
            self._platform_version
        ):
            raise PluginCompatibilityError(
                f"plugin {manifest.plugin_id} requires platform >= "
                f"{manifest.minimum_platform_version}; host is {self._platform_version}"
            )
        report = plugin.validate_config(config)
        if not report.valid:
            details = "; ".join(report.errors) or "invalid configuration"
            raise PluginRegistrationError(f"plugin {manifest.plugin_id}: {details}")
        self._plugins[manifest.plugin_id] = RegisteredPlugin(plugin=plugin, config=dict(config))

    async def start_all(self, context: PluginContext) -> dict[str, PluginHealth]:
        for item in self._plugins.values():
            item.runtime_health = PluginHealth(state=PluginState.STARTING)
            try:
                item.handle = await item.plugin.start(context, item.config)
                reported = item.plugin.health()
                item.runtime_health = reported
            except Exception as exc:  # Plugin boundary must isolate implementation failures.
                item.handle = None
                item.runtime_health = PluginHealth(
                    state=PluginState.FAILED,
                    message=f"{type(exc).__name__}: {exc}",
                )
        return self.health()

    async def stop_all(self) -> dict[str, PluginHealth]:
        for item in reversed(tuple(self._plugins.values())):
            try:
                if item.handle is not None:
                    await item.handle.stop()
            except Exception as exc:  # Continue stopping the remaining plugins.
                item.runtime_health = PluginHealth(
                    state=PluginState.FAILED,
                    message=f"{type(exc).__name__}: {exc}",
                )
            else:
                item.runtime_health = PluginHealth(state=PluginState.STOPPED)
            finally:
                item.handle = None
        return self.health()

    def health(self) -> dict[str, PluginHealth]:
        return {plugin_id: item.runtime_health for plugin_id, item in self._plugins.items()}


def _major(version: str) -> int:
    return _version_tuple(version)[0]


def _version_tuple(version: str) -> tuple[int, int, int]:
    core = version.split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise PluginCompatibilityError(f"invalid semantic version: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])
