import pytest

from nanexus_event_intelligence.alerts import COMMUNITY_POLICY, evaluate
from nanexus_event_intelligence.alerts.models import AlertFact
from nanexus_event_intelligence.localization import DEFAULT_LOCALE, system_text


def test_backend_system_messages_use_centralized_english_defaults(alert_fact: AlertFact) -> None:
    assert DEFAULT_LOCALE == "en"
    assert COMMUNITY_POLICY.version == "1.1.0"
    assert all(
        not any("\u4e00" <= char <= "\u9fff" for char in rule.description)
        for rule in COMMUNITY_POLICY.rules
    )
    result = evaluate(COMMUNITY_POLICY, alert_fact)
    assert result.reasons == ("No rule matched; shadow mode takes no action",)
    assert all(trace.explanation.startswith("Not matched:") for trace in result.trace)


def test_unknown_system_message_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown system message id"):
        system_text("unknown.message")


@pytest.fixture
def alert_fact() -> AlertFact:
    from datetime import UTC, datetime
    from uuid import uuid4

    return AlertFact(
        observation_id=uuid4(),
        event_kind="object",
        lifecycle="started",
        occurred_at=datetime.now(UTC),
        labels=frozenset({"cat"}),
    )
