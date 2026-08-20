from nanexus_event_intelligence.alerts.models import RuleMatch, ShadowPolicy, ShadowRule
from nanexus_event_intelligence.localization import system_text

COMMUNITY_POLICY = ShadowPolicy(
    policy_id="community.basic-alerts",
    version="1.1.0",
    rules=(
        ShadowRule(
            rule_id="person.priority-zone",
            priority=10,
            outcome="escalate",
            description=system_text("policy.person_priority_zone"),
            match=RuleMatch(
                labels_any=frozenset({"person"}),
                zones_any=frozenset({"porch", "entrance", "perimeter"}),
            ),
        ),
        ShadowRule(
            rule_id="person.detected",
            priority=20,
            outcome="send",
            description=system_text("policy.person_detected"),
            match=RuleMatch(labels_any=frozenset({"person"})),
        ),
        ShadowRule(
            rule_id="stationary.non-person-update",
            priority=30,
            outcome="suppress",
            description=system_text("policy.stationary_non_person_update"),
            match=RuleMatch(
                lifecycles=frozenset({"updated"}),
                require_all_objects_stationary=True,
                exclude_labels=frozenset({"person"}),
            ),
        ),
        ShadowRule(
            rule_id="vehicle.detected",
            priority=40,
            outcome="send",
            description=system_text("policy.vehicle_detected"),
            match=RuleMatch(labels_any=frozenset({"car", "truck", "bus", "motorcycle", "bicycle"})),
        ),
    ),
)
