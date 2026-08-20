from datetime import UTC, datetime
from uuid import uuid4

from nanexus_event_intelligence.alerts import COMMUNITY_POLICY, evaluate
from nanexus_event_intelligence.alerts.models import AlertFact


def fact(
    *,
    labels: set[str],
    zones: set[str] | None = None,
    lifecycle: str = "started",
    stationary: tuple[bool | None, ...] = (),
) -> AlertFact:
    return AlertFact(
        observation_id=uuid4(),
        event_kind="object",
        lifecycle=lifecycle,
        occurred_at=datetime.now(UTC),
        labels=frozenset(labels),
        zones=frozenset(zones or set()),
        object_stationary=stationary,
    )


def test_person_priority_zone_escalates_with_trace() -> None:
    result = evaluate(COMMUNITY_POLICY, fact(labels={"person"}, zones={"porch"}))
    assert result.outcome == "escalate"
    assert result.matched_rule_id == "person.priority-zone"
    assert result.trace[0].matched
    assert result.trace[0].checks["labels_any"]


def test_person_is_never_suppressed_by_stationary_rule() -> None:
    result = evaluate(
        COMMUNITY_POLICY, fact(labels={"person"}, lifecycle="updated", stationary=(True,))
    )
    assert result.outcome == "send"
    assert result.matched_rule_id == "person.detected"


def test_stationary_non_person_update_is_suppressed() -> None:
    result = evaluate(
        COMMUNITY_POLICY, fact(labels={"car"}, lifecycle="updated", stationary=(True, True))
    )
    assert result.outcome == "suppress"
    assert result.matched_rule_id == "stationary.non-person-update"


def test_missing_stationary_evidence_does_not_suppress() -> None:
    result = evaluate(COMMUNITY_POLICY, fact(labels={"car"}, lifecycle="updated"))
    assert result.outcome == "send"
    stationary_trace = next(
        item for item in result.trace if item.rule_id == "stationary.non-person-update"
    )
    assert not stationary_trace.checks["all_objects_stationary"]


def test_unknown_event_defaults_to_no_action_deterministically() -> None:
    item = fact(labels={"cat"})
    first = evaluate(COMMUNITY_POLICY, item)
    second = evaluate(COMMUNITY_POLICY, item)
    assert first == second
    assert first.outcome == "no_action"
    assert first.matched_rule_id is None
