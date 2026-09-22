from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.core.contracts import (
    EvidenceAvailability,
    EvidenceRef,
    EvidenceType,
    PrivacyPolicy,
    PrivacyRoute,
    RequestedOutputType,
)
from nanexus_event_intelligence.core.contracts import (
    ProcessorJob as ProcessorJobContract,
)
from nanexus_event_intelligence.persistence.models import ProcessorJob, ReviewItem, new_id
from nanexus_event_intelligence.processor import PUBLIC_PROCESSOR_TYPE, create_processor_job


def evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        evidence_id=new_id(),
        media_type=EvidenceType.SNAPSHOT,
        privacy_class=PrivacyRoute.LOCAL_ONLY,
        availability=EvidenceAvailability.AVAILABLE,
        purpose="caption_tags",
    )


def privacy_policy() -> PrivacyPolicy:
    return PrivacyPolicy(
        policy_id="community-local",
        policy_version="1",
        route=PrivacyRoute.LOCAL_ONLY,
        external_network_allowed=False,
        retention="none",
    )


async def test_create_processor_job_persists_public_contract(session: AsyncSession) -> None:
    review = ReviewItem(
        id=new_id(),
        status="ended",
        start_at=datetime(2026, 9, 22, tzinfo=UTC),
        source_revision="ended:3",
    )
    session.add(review)
    await session.flush()

    job = await create_processor_job(
        session,
        review_item=review,
        evidence_refs=[evidence_ref()],
        privacy_policy=privacy_policy(),
        requested_at=datetime(2026, 9, 22, 12, tzinfo=UTC),
    )
    payload = ProcessorJobContract.model_validate(job.payload)

    assert payload.job_id == job.id
    assert payload.subject_type == "review_item"
    assert payload.subject_id == review.id
    assert payload.subject_revision == "ended:3"
    assert payload.processor_type == PUBLIC_PROCESSOR_TYPE == "video_summary.caption_tags"
    assert [item.output_type for item in payload.requested_outputs] == [
        RequestedOutputType.CAPTION,
        RequestedOutputType.TAGS,
    ]
    assert job.status == "pending"
    assert job.attempt_count == 0


async def test_duplicate_construction_returns_existing_job(session: AsyncSession) -> None:
    review = ReviewItem(
        id=new_id(),
        status="ended",
        start_at=datetime(2026, 9, 22, tzinfo=UTC),
        source_revision="ended:4",
    )
    evidence = evidence_ref()
    policy = privacy_policy()
    session.add(review)
    await session.flush()

    first = await create_processor_job(
        session, review_item=review, evidence_refs=[evidence], privacy_policy=policy
    )
    second = await create_processor_job(
        session, review_item=review, evidence_refs=[evidence], privacy_policy=policy
    )

    assert second.id == first.id
    assert second.idempotency_key == first.idempotency_key
    assert await session.scalar(select(func.count()).select_from(ProcessorJob)) == 1
