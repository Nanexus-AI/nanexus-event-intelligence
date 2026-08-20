"""Deterministic Community shadow alert evaluation."""

from nanexus_event_intelligence.alerts.evaluator import evaluate
from nanexus_event_intelligence.alerts.policy import COMMUNITY_POLICY

__all__ = ["COMMUNITY_POLICY", "evaluate"]
