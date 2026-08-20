import hashlib

from nanexus_event_intelligence.alerts.evaluator import evaluate
from nanexus_event_intelligence.alerts.models import AlertFact, ShadowEvaluation, ShadowPolicy
from nanexus_event_intelligence.alerts.policy import COMMUNITY_POLICY
from nanexus_event_intelligence.replay.bundle import canonical_json
from nanexus_event_intelligence.replay.engine import SinkSafety
from nanexus_event_intelligence.replay.models import ReplayEnvelope


class ShadowDecisionDryRunSink:
    safety = SinkSafety.DRY_RUN

    def __init__(self, policy: ShadowPolicy = COMMUNITY_POLICY) -> None:
        self._policy = policy
        self._digest = hashlib.sha256()
        self.evaluations: list[ShadowEvaluation] = []

    async def emit(self, envelope: ReplayEnvelope) -> None:
        event = envelope.event
        result = evaluate(
            self._policy,
            AlertFact(
                observation_id=event.observation_id,
                event_kind=event.event_kind,
                lifecycle=event.lifecycle,
                occurred_at=event.occurred_at,
                labels=frozenset(event.labels),
                zones=frozenset(event.zones),
            ),
        )
        self.evaluations.append(result)
        self._digest.update(canonical_json(result.model_dump(mode="json")) + b"\n")

    @property
    def output_sha256(self) -> str:
        return self._digest.hexdigest()
