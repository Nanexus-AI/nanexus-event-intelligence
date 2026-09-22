import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nanexus_event_intelligence.core.contracts import Capability, EnrichmentResult, ProcessorJob

FIXTURE = json.loads((Path(__file__).parent / "fixtures/contract-v1.json").read_text())


def test_shared_fixture_validates_all_public_v1_contracts() -> None:
    ProcessorJob.model_validate(FIXTURE["processor_job"])
    Capability.model_validate(FIXTURE["capability"])
    for result in FIXTURE["enrichment_results"].values():
        EnrichmentResult.model_validate(result)


@pytest.mark.parametrize("status", ["succeeded", "abstained"])
def test_results_round_trip_without_reasoning_or_internal_fields(status: str) -> None:
    encoded = EnrichmentResult.model_validate(FIXTURE["enrichment_results"][status]).model_dump(
        mode="json"
    )
    forbidden = {"chain_of_thought", "prompt", "source_url", "credential", "orm", "frigate"}
    assert forbidden.isdisjoint(str(encoded).lower())


def test_status_claim_and_error_invariants_are_enforced() -> None:
    payload = copy.deepcopy(FIXTURE["enrichment_results"]["succeeded"])
    payload["claims"] = []
    with pytest.raises(ValidationError, match="requires claims"):
        EnrichmentResult.model_validate(payload)
    payload = copy.deepcopy(FIXTURE["enrichment_results"]["abstained"])
    payload["errors"] = []
    with pytest.raises(ValidationError, match="requires a reason"):
        EnrichmentResult.model_validate(payload)


def test_local_only_result_rejects_external_network_and_extra_secrets() -> None:
    payload = copy.deepcopy(FIXTURE["enrichment_results"]["succeeded"])
    payload["model_invocation"]["external_network_used"] = True
    with pytest.raises(ValidationError, match="local_only"):
        EnrichmentResult.model_validate(payload)
    payload = copy.deepcopy(FIXTURE["enrichment_results"]["succeeded"])
    payload["frigate_credential"] = "secret"
    with pytest.raises(ValidationError, match="Extra inputs"):
        EnrichmentResult.model_validate(payload)


def test_capability_rejects_unknown_media_type_and_invalid_limit() -> None:
    payload = copy.deepcopy(FIXTURE["capability"])
    payload["media_limits"]["allowed_content_types"].append("video/mp4")
    with pytest.raises(ValidationError):
        Capability.model_validate(payload)
    payload = copy.deepcopy(FIXTURE["capability"])
    payload["media_limits"]["max_bytes"] = 0
    with pytest.raises(ValidationError):
        Capability.model_validate(payload)


def test_normative_schemas_match_models() -> None:
    root = Path(__file__).parents[3]
    for filename, model in (
        ("enrichment-result-v1.schema.json", EnrichmentResult),
        ("capability-v1.schema.json", Capability),
    ):
        schema = json.loads((root / "docs/schemas" / filename).read_text())
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(model.model_fields)
