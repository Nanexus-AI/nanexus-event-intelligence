"""Versioned, vendor-neutral contract for trusted in-process plugins."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from nanexus_event_intelligence.core.source_adapter import ValidationReport

PLUGIN_CONTRACT_VERSION = "1.0.0"


class PluginKind(StrEnum):
    SOURCE_ADAPTER = "source_adapter"
    CONTEXT_ADAPTER = "context_adapter"
    NOTIFICATION_ADAPTER = "notification_adapter"
    MODEL_PROVIDER = "model_provider"
    POLICY_PACK = "policy_pack"
    SCENARIO_PACK = "scenario_pack"


class PluginPermission(BaseModel):
    """Declared access required by a plugin; this is auditable, not a sandbox."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    network_hosts: tuple[str, ...] = ()
    reads_media: bool = False
    writes_external_system: bool = False
    stores_data: bool = False
    secret_names: tuple[str, ...] = ()


class PluginManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=120)
    plugin_version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    contract_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    minimum_platform_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    kind: PluginKind
    capabilities: tuple[str, ...] = ()
    config_schema: dict[str, Any] = Field(default_factory=dict)
    permissions: PluginPermission = Field(default_factory=PluginPermission)


class PluginState(StrEnum):
    REGISTERED = "registered"
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class PluginHealth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: PluginState
    message: str | None = None


class PluginContext(BaseModel):
    """Stable host services exposed to plugins; expand only by contract version."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    services: Mapping[str, object] = Field(default_factory=dict)


class PluginHandle(Protocol):
    async def stop(self) -> None: ...


class CommunityPlugin(Protocol):
    @property
    def manifest(self) -> PluginManifest: ...

    def validate_config(self, config: Mapping[str, Any]) -> ValidationReport: ...

    async def start(self, context: PluginContext, config: Mapping[str, Any]) -> PluginHandle: ...

    def health(self) -> PluginHealth: ...
