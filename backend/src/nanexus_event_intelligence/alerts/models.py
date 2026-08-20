from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Outcome = Literal["send", "suppress", "escalate", "no_action"]


class RuleMatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_kinds: frozenset[str] = frozenset()
    lifecycles: frozenset[str] = frozenset()
    labels_any: frozenset[str] = frozenset()
    zones_any: frozenset[str] = frozenset()
    require_all_objects_stationary: bool | None = None
    exclude_labels: frozenset[str] = frozenset()


class ShadowRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(pattern=r"^[a-z][a-z0-9._-]+$")
    priority: int = Field(ge=0)
    outcome: Outcome
    description: str
    match: RuleMatch


class ShadowPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str
    version: str
    rules: tuple[ShadowRule, ...]
    default_outcome: Literal["no_action"] = "no_action"


class AlertFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: UUID
    event_kind: str
    lifecycle: str
    occurred_at: datetime
    labels: frozenset[str] = frozenset()
    zones: frozenset[str] = frozenset()
    object_stationary: tuple[bool | None, ...] = ()


class RuleTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    priority: int
    matched: bool
    checks: dict[str, bool]
    explanation: str


class ShadowEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: Outcome
    policy_id: str
    policy_version: str
    matched_rule_id: str | None
    reasons: tuple[str, ...]
    trace: tuple[RuleTrace, ...]
