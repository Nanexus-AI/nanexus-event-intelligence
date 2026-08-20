from nanexus_event_intelligence.alerts.models import (
    AlertFact,
    RuleTrace,
    ShadowEvaluation,
    ShadowPolicy,
    ShadowRule,
)
from nanexus_event_intelligence.localization import system_text


def evaluate(policy: ShadowPolicy, fact: AlertFact) -> ShadowEvaluation:
    traces: list[RuleTrace] = []
    for rule in sorted(policy.rules, key=lambda item: (item.priority, item.rule_id)):
        trace = _evaluate_rule(rule, fact)
        traces.append(trace)
        if trace.matched:
            return ShadowEvaluation(
                outcome=rule.outcome,
                policy_id=policy.policy_id,
                policy_version=policy.version,
                matched_rule_id=rule.rule_id,
                reasons=(rule.description,),
                trace=tuple(traces),
            )
    return ShadowEvaluation(
        outcome=policy.default_outcome,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        matched_rule_id=None,
        reasons=(system_text("evaluation.no_rule_matched"),),
        trace=tuple(traces),
    )


def _evaluate_rule(rule: ShadowRule, fact: AlertFact) -> RuleTrace:
    match = rule.match
    checks = {
        "event_kind": not match.event_kinds or fact.event_kind in match.event_kinds,
        "lifecycle": not match.lifecycles or fact.lifecycle in match.lifecycles,
        "labels_any": not match.labels_any or bool(fact.labels & match.labels_any),
        "zones_any": not match.zones_any or bool(fact.zones & match.zones_any),
        "exclude_labels": not bool(fact.labels & match.exclude_labels),
        "all_objects_stationary": _stationary_matches(
            match.require_all_objects_stationary, fact.object_stationary
        ),
    }
    matched = all(checks.values())
    failed = [name for name, passed in checks.items() if not passed]
    explanation = (
        rule.description
        if matched
        else system_text("evaluation.rule_not_matched", failed_checks=", ".join(failed))
    )
    return RuleTrace(
        rule_id=rule.rule_id,
        priority=rule.priority,
        matched=matched,
        checks=checks,
        explanation=explanation,
    )


def _stationary_matches(required: bool | None, values: tuple[bool | None, ...]) -> bool:
    if required is None:
        return True
    if not values or any(value is None for value in values):
        return False
    return all(values) if required else not all(values)
