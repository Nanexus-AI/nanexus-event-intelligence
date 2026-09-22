"""Construct and persist transport-neutral jobs for an external processor."""

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.core.contracts.processor_job import (
    EvidenceRef,
    PrivacyPolicy,
    RequestedOutput,
    RequestedOutputType,
    SubjectType,
)
from nanexus_event_intelligence.core.contracts.processor_job import (
    ProcessorJob as ProcessorJobContract,
)
from nanexus_event_intelligence.persistence.models import (
    ProcessorJob,
    ReviewItem,
    new_id,
    utc_now,
)

PUBLIC_PROCESSOR_TYPE = "video_summary.caption_tags"
CONTRACT_VERSION: Literal["1.0"] = "1.0"


def processor_job_idempotency_key(
    *,
    review_item_id: UUID,
    subject_revision: str,
    evidence_refs: Sequence[EvidenceRef],
    privacy_policy: PrivacyPolicy,
) -> str:
    """Return a stable identity for one revision, evidence set, and policy."""
    material = {
        "contract_version": CONTRACT_VERSION,
        "processor_type": PUBLIC_PROCESSOR_TYPE,
        "subject_type": SubjectType.REVIEW_ITEM,
        "subject_id": str(review_item_id),
        "subject_revision": subject_revision,
        "evidence": sorted(
            (item.model_dump(mode="json") for item in evidence_refs),
            key=lambda item: item["evidence_id"],
        ),
        "outputs": [RequestedOutputType.CAPTION, RequestedOutputType.TAGS],
        "privacy_policy": privacy_policy.model_dump(mode="json"),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return "processor-job:v1:" + hashlib.sha256(encoded).hexdigest()


async def create_processor_job(
    session: AsyncSession,
    *,
    review_item: ReviewItem,
    evidence_refs: Sequence[EvidenceRef],
    privacy_policy: PrivacyPolicy,
    requested_at: datetime | None = None,
    trace_id: UUID | None = None,
) -> ProcessorJob:
    """Persist one idempotent job without scheduling or executing processor work."""
    if not evidence_refs:
        raise ValueError("at least one evidence reference is required")

    ordered_evidence = tuple(sorted(evidence_refs, key=lambda item: str(item.evidence_id)))
    idempotency_key = processor_job_idempotency_key(
        review_item_id=review_item.id,
        subject_revision=review_item.source_revision,
        evidence_refs=ordered_evidence,
        privacy_policy=privacy_policy,
    )
    existing = await session.scalar(
        select(ProcessorJob).where(ProcessorJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing

    now = requested_at or utc_now()
    job_id = new_id()
    contract = ProcessorJobContract(
        job_id=job_id,
        contract_version=CONTRACT_VERSION,
        processor_type=PUBLIC_PROCESSOR_TYPE,
        subject_type=SubjectType.REVIEW_ITEM,
        subject_id=review_item.id,
        subject_revision=review_item.source_revision,
        evidence_refs=ordered_evidence,
        requested_outputs=(
            RequestedOutput(
                output_type=RequestedOutputType.CAPTION,
                schema_version=CONTRACT_VERSION,
                required=True,
            ),
            RequestedOutput(
                output_type=RequestedOutputType.TAGS,
                schema_version=CONTRACT_VERSION,
                required=True,
            ),
        ),
        privacy_policy=privacy_policy,
        idempotency_key=idempotency_key,
        requested_at=now,
        trace_id=trace_id or new_id(),
    )
    job = ProcessorJob(
        id=job_id,
        processor_type=contract.processor_type,
        subject_type=contract.subject_type,
        subject_id=contract.subject_id,
        subject_revision=contract.subject_revision,
        contract_version=contract.contract_version,
        idempotency_key=contract.idempotency_key,
        trace_id=contract.trace_id,
        status="pending",
        payload=contract.model_dump(mode="json"),
        available_at=now,
    )
    session.add(job)
    await session.flush()
    return job
