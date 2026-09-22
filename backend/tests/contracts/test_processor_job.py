import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from nanexus_event_intelligence.core.contracts import (
    PROCESSOR_CONTRACT_VERSION,
    ProcessorJob,
)

JOB = {
    "job_id": "018f47d2-bd80-7a12-86d3-2e8f7961f72c",
    "contract_version": "1.0",
    "processor_type": "video_summary.caption_tags",
    "subject_type": "review_item",
    "subject_id": "018f47d2-c3aa-7dd0-80e2-1f73adf8eb10",
    "subject_revision": "ended:3",
    "evidence_refs": [
        {
            "evidence_id": "018f47d2-c784-7834-8232-362fad70f41f",
            "media_type": "snapshot",
            "privacy_class": "local_only",
            "availability": "available",
            "purpose": "representative",
        }
    ],
    "requested_outputs": [
        {"output_type": "caption", "schema_version": "1.0", "required": True},
        {"output_type": "tags", "schema_version": "1.0", "required": True},
    ],
    "privacy_policy": {
        "policy_id": "default-local",
        "policy_version": "1.0.0",
        "route": "local_only",
        "external_network_allowed": False,
        "retention": "none",
    },
    "idempotency_key": (
        "processor-job:review_item:018f47d2-c3aa-7dd0-80e2-1f73adf8eb10:"
        "ended:3:video_summary.caption_tags:1.0"
    ),
    "requested_at": "2026-08-21T16:00:00Z",
    "trace_id": "018f47d2-cc90-75e1-b9c3-e00e70c18831",
}


def test_valid_job_round_trips_without_transport_or_orm_fields() -> None:
    job = ProcessorJob.model_validate(JOB)
    encoded = job.model_dump(mode="json")
    assert job.contract_version == PROCESSOR_CONTRACT_VERSION
    assert job.requested_at == datetime(2026, 8, 21, 16, tzinfo=UTC)
    assert encoded["subject_type"] == "review_item"
    assert UUID(encoded["evidence_refs"][0]["evidence_id"])
    forbidden = {"source_ref", "url", "frigate_id", "credential", "redis_stream"}
    assert forbidden.isdisjoint(str(encoded).lower())


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("contract_version",), "2.0"),
        (("subject_type",), "observation"),
        (("requested_at",), "2026-08-21T16:00:00"),
        (("evidence_refs", 0, "media_type"), "clip"),
    ],
)
def test_rejects_unsupported_v1_values(path: tuple[object, ...], value: object) -> None:
    import copy

    payload = copy.deepcopy(JOB)
    target = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        ProcessorJob.model_validate(payload)


def test_rejects_source_url_credentials_and_internal_transport_fields() -> None:
    for field, value in (
        ("source_url", "http://frigate.local/api/events/1/snapshot.jpg"),
        ("credential", "secret"),
        ("redis_stream", "nanexus:canonical-events"),
    ):
        payload = {**JOB, field: value}
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            ProcessorJob.model_validate(payload)


def test_rejects_duplicate_outputs_and_unsafe_local_policy() -> None:
    duplicate = {**JOB, "requested_outputs": [JOB["requested_outputs"][0]] * 2}
    with pytest.raises(ValidationError, match="must be unique"):
        ProcessorJob.model_validate(duplicate)

    unsafe = {**JOB, "privacy_policy": {**JOB["privacy_policy"], "external_network_allowed": True}}
    with pytest.raises(ValidationError, match="local_only"):
        ProcessorJob.model_validate(unsafe)


def test_normative_schema_matches_v1_model_surface() -> None:
    repository = Path(__file__).parents[3]
    schema = json.loads(
        (repository / "docs/schemas/processor-job-v1.schema.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["contract_version"] == {"const": "1.0"}
    assert set(schema["required"]) == set(ProcessorJob.model_fields)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["subject_type"] == {"const": "review_item"}


def test_contract_module_has_no_orm_transport_adapter_or_provider_imports() -> None:
    source = (
        Path(__file__).parents[2] / "src/nanexus_event_intelligence/core/contracts/processor_job.py"
    )
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    forbidden = (
        "nanexus_event_intelligence.persistence",
        "nanexus_event_intelligence.pipeline",
        "nanexus_event_intelligence.adapters",
        "open_clip",
        "torch",
    )
    assert not any(module.startswith(forbidden) for module in imports)
