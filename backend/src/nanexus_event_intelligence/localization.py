from collections.abc import Mapping

DEFAULT_LOCALE = "en"

_ENGLISH_MESSAGES: Mapping[str, str] = {
    "policy.person_priority_zone": "Person entered a priority zone; shadow escalation recommended",
    "policy.person_detected": "Person detected; shadow notification recommended",
    "policy.stationary_non_person_update": (
        "All non-person objects are stationary in an update; "
        "duplicate shadow notification suppressed"
    ),
    "policy.vehicle_detected": "Vehicle-class object detected; shadow notification recommended",
    "evaluation.no_rule_matched": "No rule matched; shadow mode takes no action",
    "evaluation.rule_not_matched": "Not matched: {failed_checks}",
    "notification.title.escalate": "Event requires attention",
    "notification.title.send": "Event detected",
    "notification.body.fallback": "Rule recommends sending a notification",
    "demo.camera.entry": "Community Demo Entrance",
}


def system_text(message_id: str, /, **values: object) -> str:
    """Render system-owned canonical text in the backend's default locale."""
    try:
        template = _ENGLISH_MESSAGES[message_id]
    except KeyError as error:
        raise ValueError(f"unknown system message id: {message_id}") from error
    return template.format(**values)
