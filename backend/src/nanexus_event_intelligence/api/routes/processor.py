"""Authenticated, job-scoped Processor API v1."""

import hashlib
import hmac
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.api.dependencies import get_session
from nanexus_event_intelligence.config import get_settings
from nanexus_event_intelligence.core.contracts.capability import Capability, MediaLimits
from nanexus_event_intelligence.core.contracts.enrichment_result import EnrichmentResult
from nanexus_event_intelligence.core.contracts.processor_job import ProcessorJob as JobContract
from nanexus_event_intelligence.core.evidence import (
    EvidenceContentReader,
    EvidenceContentRequest,
    EvidenceContentUnavailable,
)
from nanexus_event_intelligence.persistence.models import (
    AuditRecord,
    Camera,
    Claim,
    ClaimEvidence,
    Evidence,
    ModelInvocation,
    ModelInvocationEvidence,
    Observation,
    ProcessorJob,
    ReviewItem,
    SourceInstance,
    utc_now,
)

router = APIRouter(prefix="/processor", tags=["processor"])
PROCESSOR_READABLE_STATES = frozenset({"running", "succeeded", "abstained", "failed"})


def require_processor_identity(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    secret = get_settings().processor_api_token
    expected = secret.get_secret_value() if secret else ""
    scheme, separator, supplied = (authorization or "").partition(" ")
    valid_scheme = separator == " " and scheme.lower() == "bearer"
    if not expected or not valid_scheme or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="processor identity denied",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "video-summary"


class SubjectMetadata(BaseModel):
    subject_type: str
    subject_id: UUID
    subject_revision: str
    lifecycle: str
    labels: list[str]
    zones: list[str]
    camera: str | None
    site: str | None
    occurred_at: datetime


class SubmitReceipt(BaseModel):
    job_id: UUID
    status: str
    accepted: bool
    claim_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


@router.get("/capabilities", response_model=Capability)
async def capabilities(_: str = Depends(require_processor_identity)) -> Capability:
    return Capability(
        capability_contract_version="1.0",
        platform_version="0.1.0",
        api_versions=("1.0",),
        canonical_schema_versions=("1.0",),
        processor_contract_versions=("1.0",),
        enrichment_result_versions=("1.0",),
        supported_subject_types=("review_item",),
        supported_evidence_types=("snapshot",),
        claim_writeback=True,
        model_invocation=True,
        replay=True,
        dry_run=False,
        media_limits=MediaLimits(
            max_bytes=10 * 1024 * 1024,
            allowed_content_types=("image/jpeg", "image/png", "image/webp"),
        ),
    )


async def _job(session: AsyncSession, job_id: UUID) -> ProcessorJob:
    job = await session.get(ProcessorJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="processor job not found")
    return job


@router.get("/jobs/next", response_model=JobContract | None)
async def next_job(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: str = Depends(require_processor_identity),
) -> JobContract | None:
    now = utc_now()
    job = await session.scalar(
        select(ProcessorJob)
        .where(
            ProcessorJob.status.in_(("pending", "retry_wait")),
            ProcessorJob.available_at <= now,
        )
        .order_by(ProcessorJob.available_at, ProcessorJob.created_at, ProcessorJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    contract = JobContract.model_validate(job.payload)
    job.status = "running"
    job.attempt_count += 1
    job.started_at = now
    return contract


@router.get("/jobs/{job_id}/subject", response_model=SubjectMetadata)
async def subject_metadata(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: str = Depends(require_processor_identity),
) -> SubjectMetadata:
    job = await _job(session, job_id)
    if job.status not in PROCESSOR_READABLE_STATES or job.subject_type != "review_item":
        raise HTTPException(status_code=404, detail="job subject not found")
    review = await session.get(ReviewItem, job.subject_id)
    if review is None:
        raise HTTPException(status_code=404, detail="job subject not found")
    camera_row = (
        (
            await session.execute(
                select(Camera.name, Camera.site_id).where(Camera.id == review.camera_id)
            )
        ).one_or_none()
        if review.camera_id
        else None
    )
    return SubjectMetadata(
        subject_type=job.subject_type,
        subject_id=review.id,
        subject_revision=job.subject_revision,
        lifecycle=review.status,
        labels=review.labels,
        zones=review.zones,
        camera=camera_row[0] if camera_row else None,
        site=camera_row[1] if camera_row else None,
        occurred_at=review.start_at,
    )


@router.get("/jobs/{job_id}/evidence/{evidence_id}")
async def evidence_content(
    job_id: UUID,
    evidence_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: str = Depends(require_processor_identity),
) -> Response:
    job = await _job(session, job_id)
    if job.status not in PROCESSOR_READABLE_STATES:
        raise HTTPException(status_code=409, detail="processor job is not readable")
    contract = JobContract.model_validate(job.payload)
    reference = next(
        (item for item in contract.evidence_refs if item.evidence_id == evidence_id), None
    )
    if reference is None:
        raise HTTPException(status_code=403, detail="evidence is outside this job grant")
    row = (
        await session.execute(
            select(Evidence, Observation, SourceInstance)
            .join(Observation, Observation.id == Evidence.observation_id)
            .join(SourceInstance, SourceInstance.id == Evidence.source_instance_id)
            .where(Evidence.id == evidence_id)
        )
    ).one_or_none()
    if row is None or reference.availability != "available":
        raise HTTPException(status_code=404, detail="evidence unavailable")
    _, observation, source = row
    reader: EvidenceContentReader = request.app.state.evidence_content_reader
    try:
        media = await reader.read(
            EvidenceContentRequest(
                evidence_id=evidence_id,
                source_type=source.source_type,
                source_namespace=observation.source_namespace,
                source_entity_id=observation.source_entity_id,
                extensions=observation.extensions,
            )
        )
    except EvidenceContentUnavailable as error:
        raise HTTPException(
            status_code=503 if error.retryable else 404,
            detail="evidence content unavailable",
        ) from None
    return Response(
        media.content,
        media_type=media.content_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/jobs/{job_id}/result", response_model=SubmitReceipt)
async def submit_result(
    job_id: UUID,
    result: EnrichmentResult,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: str = Depends(require_processor_identity),
) -> SubmitReceipt:
    job = await _job(session, job_id)
    if result.job_id != job.id or result.idempotency_key != job.idempotency_key:
        raise HTTPException(status_code=409, detail="result does not match processor job")
    existing = await session.scalar(
        select(ModelInvocation).where(ModelInvocation.processor_job_id == job.id)
    )
    if existing is not None:
        existing_claim_ids = list(
            await session.scalars(select(Claim.id).where(Claim.model_invocation_id == existing.id))
        )
        evidence_ids = list(
            await session.scalars(
                select(ModelInvocationEvidence.evidence_id).where(
                    ModelInvocationEvidence.model_invocation_id == existing.id
                )
            )
        )
        return SubmitReceipt(
            job_id=job.id,
            status=job.status,
            accepted=False,
            claim_ids=existing_claim_ids,
            evidence_ids=sorted(evidence_ids, key=str),
        )
    if job.status != "running":
        raise HTTPException(status_code=409, detail="processor job is not running")
    contract = JobContract.model_validate(job.payload)
    granted = {item.evidence_id for item in contract.evidence_refs}
    submitted = {item for claim in result.claims for item in claim.evidence_ids}
    if not submitted.issubset(granted):
        raise HTTPException(status_code=403, detail="claim evidence is outside this job grant")
    policy = contract.privacy_policy
    facts = result.model_invocation
    if facts.privacy_route.value != policy.route.value:
        raise HTTPException(status_code=409, detail="result privacy route violates job policy")
    if facts.external_network_used and not policy.external_network_allowed:
        raise HTTPException(status_code=409, detail="external network use violates job policy")

    invocation = ModelInvocation(
        processor_job_id=job.id,
        provider=facts.provider,
        model=facts.model,
        runtime_version=facts.model_version,
        prompt_version="processor-contract-v1",
        schema_version=result.contract_version,
        privacy_route=facts.privacy_route,
        status=result.status,
        started_at=facts.started_at,
        completed_at=facts.completed_at,
        latency_ms=max(0, int((facts.completed_at - facts.started_at).total_seconds() * 1000)),
        external_network_used=facts.external_network_used,
        error_code=result.errors[0].code if result.errors else None,
        error_message=result.errors[0].reason if result.errors else None,
        result_hash=hashlib.sha256(result.model_dump_json().encode()).hexdigest(),
    )
    session.add(invocation)
    await session.flush()
    claim_ids: list[UUID] = []
    for wire_claim in result.claims:
        value: dict[str, Any] = (
            {"text": wire_claim.text}
            if wire_claim.claim_type == "caption"
            else {"tags": list(wire_claim.tags)}
        )
        claim = Claim(
            review_item_id=job.subject_id,
            model_invocation_id=invocation.id,
            producer_type="model",
            producer_version=f"{facts.model}@{facts.model_version}",
            predicate=wire_claim.claim_type,
            value=value,
            confidence=wire_claim.confidence,
        )
        session.add(claim)
        await session.flush()
        claim_ids.append(claim.id)
        for evidence_id in wire_claim.evidence_ids:
            session.add(ClaimEvidence(claim_id=claim.id, evidence_id=evidence_id))
    for evidence_id in sorted(submitted, key=str):
        session.add(
            ModelInvocationEvidence(model_invocation_id=invocation.id, evidence_id=evidence_id)
        )
    job.status = result.status
    job.completed_at = result.completed_at
    job.last_error_code = result.errors[0].code if result.errors else None
    job.last_error = result.errors[0].reason if result.errors else None
    session.add(
        AuditRecord(
            actor=f"processor:{actor}",
            action="enrichment_result.accepted",
            target_type="processor_job",
            target_id=job.id,
            before={"status": "running"},
            after={"status": job.status},
            metadata_json={
                "trace_id": str(job.trace_id),
                "contract_version": result.contract_version,
            },
        )
    )
    return SubmitReceipt(
        job_id=job.id,
        status=job.status,
        accepted=True,
        claim_ids=claim_ids,
        evidence_ids=sorted(submitted, key=str),
    )
