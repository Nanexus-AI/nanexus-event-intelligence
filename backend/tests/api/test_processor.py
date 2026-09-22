from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.config import get_settings
from nanexus_event_intelligence.core.contracts.capability import Capability
from nanexus_event_intelligence.core.contracts.enrichment_result import (
    CaptionClaim,
    EnrichmentResult,
    ModelInvocationFacts,
    PrivacyRoute,
    ResultError,
    ResultStatus,
    TagsClaim,
)
from nanexus_event_intelligence.core.contracts.processor_job import (
    EvidenceAvailability,
    EvidenceRef,
    EvidenceType,
    PrivacyPolicy,
)
from nanexus_event_intelligence.core.evidence import EvidenceContent, EvidenceContentUnavailable
from nanexus_event_intelligence.main import create_app
from nanexus_event_intelligence.persistence.models import (
    Base,
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
)
from nanexus_event_intelligence.processor import create_processor_job


class FakeReader:
    def __init__(self, error: EvidenceContentUnavailable | None = None) -> None:
        self.error = error

    async def read(self, _request):
        if self.error:
            raise self.error
        return EvidenceContent(content=b"fixture-image", content_type="image/jpeg")


async def _app(monkeypatch, *, configured: bool = True):
    if configured:
        monkeypatch.setenv("PROCESSOR_API_TOKEN", "processor-secret")
    else:
        monkeypatch.delenv("PROCESSOR_API_TOKEN", raising=False)
    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory.begin() as session:
        source = SourceInstance(
            source_type="frigate", name="test", adapter_version="1.0", capabilities={}
        )
        camera = Camera(site_id="home", name="front", display_name="Front", timezone="UTC")
        session.add_all((source, camera))
        await session.flush()
        observation = Observation(
            source_instance_id=source.id,
            camera_id=camera.id,
            source_namespace="frigate.event",
            source_entity_id="event-1",
            source_revision="1",
            dedupe_key="event-1:1",
            schema_version="1.0",
            event_kind="object",
            lifecycle="ended",
            occurred_at=now,
            observed_at=now,
            labels=["person"],
            zones=["porch"],
        )
        review = ReviewItem(
            camera_id=camera.id,
            status="ended",
            start_at=now,
            labels=["person"],
            zones=["porch"],
            source_revision="1",
        )
        session.add_all((observation, review))
        await session.flush()
        evidence = Evidence(
            source_instance_id=source.id,
            observation_id=observation.id,
            media_type="snapshot",
            source_ref="private://event-1",
            privacy_class="local_only",
            availability="available",
        )
        session.add(evidence)
        await session.flush()
        job = await create_processor_job(
            session,
            review_item=review,
            evidence_refs=(
                EvidenceRef(
                    evidence_id=evidence.id,
                    media_type=EvidenceType.SNAPSHOT,
                    privacy_class=PrivacyRoute.LOCAL_ONLY,
                    availability=EvidenceAvailability.AVAILABLE,
                    purpose="caption",
                ),
            ),
            privacy_policy=PrivacyPolicy(
                policy_id="local",
                policy_version="1",
                route="local_only",
                external_network_allowed=False,
                retention="none",
            ),
            requested_at=now,
        )
        ids = job.id, review.id, evidence.id
    app = create_app(factory)
    app.state.evidence_content_reader = FakeReader()
    return app, factory, engine, ids


def _result(job: ProcessorJob, evidence_id, status: ResultStatus) -> EnrichmentResult:
    now = datetime.now(UTC)
    errors = (
        ()
        if status is ResultStatus.SUCCEEDED
        else (ResultError(code="no_result", reason="No usable result", retryable=False),)
    )
    claims = (
        (
            CaptionClaim(
                claim_type="caption",
                schema_version="1.0",
                text="A person is at the front door.",
                confidence=0.9,
                evidence_ids=(evidence_id,),
            ),
            TagsClaim(
                claim_type="tags",
                schema_version="1.0",
                tags=("person", "door"),
                confidence=0.8,
                evidence_ids=(evidence_id,),
            ),
        )
        if status is ResultStatus.SUCCEEDED
        else ()
    )
    return EnrichmentResult(
        job_id=job.id,
        idempotency_key=job.idempotency_key,
        contract_version="1.0",
        status=status,
        model_invocation=ModelInvocationFacts(
            invocation_id=uuid4(),
            provider="video-summary",
            model="caption-tags",
            model_version="1",
            outcome=status,
            started_at=now - timedelta(seconds=1),
            completed_at=now,
            privacy_route=PrivacyRoute.LOCAL_ONLY,
            external_network_used=False,
        ),
        claims=claims,
        errors=errors,
        completed_at=now,
    )


async def test_authentication_fails_closed_and_accepts_valid_token(monkeypatch) -> None:
    app, _, engine, _ = await _app(monkeypatch, configured=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/v1/processor/capabilities")).status_code == 401
        assert (
            await client.get(
                "/api/v1/processor/capabilities",
                headers={"Authorization": "Bearer anything"},
            )
        ).status_code == 401
    await engine.dispose()
    app, _, engine, _ = await _app(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/v1/processor/capabilities")).status_code == 401
        assert (
            await client.get(
                "/api/v1/processor/capabilities",
                headers={"Authorization": "Bearer wrong"},
            )
        ).status_code == 401
        response = await client.get(
            "/api/v1/processor/capabilities",
            headers={"Authorization": "Bearer processor-secret"},
        )
        assert response.status_code == 200
        capability = Capability.model_validate(response.json())
        assert capability.processor_contract_versions == ("1.0",)
    await engine.dispose()
    get_settings.cache_clear()


async def test_claim_subject_and_evidence_are_job_scoped(monkeypatch) -> None:
    app, factory, engine, (job_id, review_id, evidence_id) = await _app(monkeypatch)
    headers = {"Authorization": "Bearer processor-secret"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        claimed = await client.get("/api/v1/processor/jobs/next", headers=headers)
        assert claimed.status_code == 200
        assert claimed.json()["job_id"] == str(job_id)
        assert "source_ref" not in claimed.text
        assert (await client.get("/api/v1/processor/jobs/next", headers=headers)).json() is None
        subject = await client.get(f"/api/v1/processor/jobs/{job_id}/subject", headers=headers)
        assert subject.json()["subject_id"] == str(review_id)
        assert subject.json()["camera"] == "front"
        denied = await client.get(
            f"/api/v1/processor/jobs/{job_id}/evidence/{uuid4()}", headers=headers
        )
        assert denied.status_code == 403
        content = await client.get(
            f"/api/v1/processor/jobs/{job_id}/evidence/{evidence_id}", headers=headers
        )
        assert content.content == b"fixture-image"
        assert content.headers["cache-control"] == "private, no-store"
        assert content.headers["x-content-type-options"] == "nosniff"
        app.state.evidence_content_reader = FakeReader(
            EvidenceContentUnavailable("temporarily_unavailable", retryable=True)
        )
        unavailable = await client.get(
            f"/api/v1/processor/jobs/{job_id}/evidence/{evidence_id}", headers=headers
        )
        assert unavailable.status_code == 503
    async with factory() as session:
        stored = await session.get(ProcessorJob, job_id)
        assert stored is not None and stored.status == "running"
        assert stored.attempt_count == 1 and stored.started_at is not None
    await engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize("readable_status", ["running", "succeeded", "abstained", "failed"])
async def test_subject_and_granted_evidence_are_readable_without_mutation(
    monkeypatch, readable_status
) -> None:
    app, factory, engine, (job_id, review_id, evidence_id) = await _app(monkeypatch)
    headers = {"Authorization": "Bearer processor-secret"}
    async with factory.begin() as session:
        job = await session.get(ProcessorJob, job_id)
        assert job is not None
        job.status = readable_status
        job.attempt_count = 3
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        subject = await client.get(f"/api/v1/processor/jobs/{job_id}/subject", headers=headers)
        assert subject.status_code == 200
        assert subject.json()["subject_id"] == str(review_id)
        content = await client.get(
            f"/api/v1/processor/jobs/{job_id}/evidence/{evidence_id}", headers=headers
        )
        assert content.status_code == 200
        assert content.content == b"fixture-image"
        assert content.headers["cache-control"] == "private, no-store"
        assert content.headers["x-content-type-options"] == "nosniff"
        denied = await client.get(
            f"/api/v1/processor/jobs/{job_id}/evidence/{uuid4()}", headers=headers
        )
        assert denied.status_code == 403
    async with factory() as session:
        stored = await session.get(ProcessorJob, job_id)
        assert stored is not None and stored.status == readable_status
        assert stored.attempt_count == 3
        assert await session.scalar(select(func.count()).select_from(ModelInvocation)) == 0
        assert await session.scalar(select(func.count()).select_from(Claim)) == 0
    await engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize("unreadable_status", ["pending", "retry_wait"])
async def test_preclaim_subject_and_evidence_remain_unreadable(
    monkeypatch, unreadable_status
) -> None:
    app, factory, engine, (job_id, _, evidence_id) = await _app(monkeypatch)
    headers = {"Authorization": "Bearer processor-secret"}
    async with factory.begin() as session:
        job = await session.get(ProcessorJob, job_id)
        assert job is not None
        job.status = unreadable_status
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        subject = await client.get(f"/api/v1/processor/jobs/{job_id}/subject", headers=headers)
        evidence = await client.get(
            f"/api/v1/processor/jobs/{job_id}/evidence/{evidence_id}", headers=headers
        )
        assert subject.status_code == 404
        assert evidence.status_code == 409
    async with factory() as session:
        stored = await session.get(ProcessorJob, job_id)
        assert stored is not None and stored.status == unreadable_status
    await engine.dispose()
    get_settings.cache_clear()


async def test_terminal_reads_survive_application_recreation(monkeypatch) -> None:
    app, factory, engine, (job_id, review_id, evidence_id) = await _app(monkeypatch)
    del app
    async with factory.begin() as session:
        job = await session.get(ProcessorJob, job_id)
        assert job is not None
        job.status = "succeeded"
    restarted = create_app(factory)
    restarted.state.evidence_content_reader = FakeReader()
    headers = {"Authorization": "Bearer processor-secret"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        subject = await client.get(f"/api/v1/processor/jobs/{job_id}/subject", headers=headers)
        evidence = await client.get(
            f"/api/v1/processor/jobs/{job_id}/evidence/{evidence_id}", headers=headers
        )
        assert subject.status_code == 200
        assert subject.json()["subject_id"] == str(review_id)
        assert evidence.status_code == 200
        assert evidence.content == b"fixture-image"
    async with factory() as session:
        stored = await session.get(ProcessorJob, job_id)
        assert stored is not None and stored.status == "succeeded"
    await engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize("terminal", list(ResultStatus))
async def test_terminal_results_persist_and_are_idempotent(monkeypatch, terminal) -> None:
    app, factory, engine, (job_id, review_id, evidence_id) = await _app(monkeypatch)
    headers = {"Authorization": "Bearer processor-secret"}
    async with factory() as session:
        job = await session.get(ProcessorJob, job_id)
        assert job is not None
        result = _result(job, evidence_id, terminal)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.get("/api/v1/processor/jobs/next", headers=headers)
        path = f"/api/v1/processor/jobs/{job_id}/result"
        first = await client.post(path, headers=headers, json=result.model_dump(mode="json"))
        second = await client.post(path, headers=headers, json=result.model_dump(mode="json"))
        assert first.status_code == second.status_code == 200
        assert first.json()["accepted"] is True
        assert second.json()["accepted"] is False
        assert second.json()["claim_ids"] == first.json()["claim_ids"]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ModelInvocation)) == 1
        expected_claims = 2 if terminal is ResultStatus.SUCCEEDED else 0
        assert await session.scalar(select(func.count()).select_from(Claim)) == expected_claims
        claim_evidence_count = await session.scalar(select(func.count()).select_from(ClaimEvidence))
        assert claim_evidence_count == expected_claims
        evidence_links = await session.scalar(
            select(func.count()).select_from(ModelInvocationEvidence)
        )
        assert evidence_links == (1 if terminal is ResultStatus.SUCCEEDED else 0)
        stored = await session.get(ProcessorJob, job_id)
        assert stored is not None and stored.status == terminal
        for claim in await session.scalars(select(Claim)):
            assert claim.review_item_id == review_id
    await engine.dispose()
    get_settings.cache_clear()


async def test_ungranted_evidence_and_external_network_are_rejected(monkeypatch) -> None:
    app, factory, engine, (job_id, _, evidence_id) = await _app(monkeypatch)
    headers = {"Authorization": "Bearer processor-secret"}
    async with factory() as session:
        job = await session.get(ProcessorJob, job_id)
        assert job is not None
        result = _result(job, evidence_id, ResultStatus.SUCCEEDED)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.get("/api/v1/processor/jobs/next", headers=headers)
        payload = result.model_dump(mode="json")
        payload["claims"][0]["evidence_ids"] = [str(uuid4())]
        response = await client.post(
            f"/api/v1/processor/jobs/{job_id}/result", headers=headers, json=payload
        )
        assert response.status_code == 403
        payload = result.model_dump(mode="json")
        payload["model_invocation"]["privacy_route"] = "cloud_allowed"
        payload["model_invocation"]["external_network_used"] = True
        response = await client.post(
            f"/api/v1/processor/jobs/{job_id}/result", headers=headers, json=payload
        )
        assert response.status_code == 409
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ModelInvocation)) == 0
    await engine.dispose()
    get_settings.cache_clear()
