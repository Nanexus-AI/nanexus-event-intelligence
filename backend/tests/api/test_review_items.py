"""Canonical ReviewItem identity and enrichment readback contract."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.adapters.frigate.pipeline import FrigateIngestPipeline
from nanexus_event_intelligence.adapters.frigate.replay import load_fixture_bundle
from nanexus_event_intelligence.config import get_settings
from nanexus_event_intelligence.core.contracts.enrichment_result import (
    CaptionClaim,
    EnrichmentResult,
    ModelInvocationFacts,
    PrivacyRoute,
    ResultStatus,
    TagsClaim,
)
from nanexus_event_intelligence.main import create_app
from nanexus_event_intelligence.persistence.models import (
    Base,
    Camera,
    Observation,
    ReviewItem,
    SourceEntityMap,
    SourceInstance,
)
from nanexus_event_intelligence.persistence.repositories import (
    NewObservation,
    ObservationRepository,
)

BUNDLE = Path(__file__).parents[3] / "fixtures" / "frigate" / "0.17" / "vehicle-lifecycle"


async def test_review_item_identity_latest_observation_and_enrichment(monkeypatch) -> None:
    monkeypatch.setenv("PROCESSOR_API_TOKEN", "processor-secret")
    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        source = SourceInstance(
            source_type="frigate",
            name="review-item-lookup",
            adapter_version="1.0",
            capabilities={},
        )
        camera = Camera(
            site_id="home", name="camera_1", display_name="Front", timezone="America/Toronto"
        )
        session.add_all((source, camera))
        await session.flush()
        pipeline = FrigateIngestPipeline(
            session, source_instance_id=source.id, camera_ids={"camera_1": camera.id}
        )
        for index, message in enumerate(load_fixture_bundle(BUNDLE)):
            await pipeline.ingest(message, stream="lookup", cursor=str(index))
        review = await session.scalar(select(ReviewItem))
        ended = await session.scalar(
            select(Observation).where(
                Observation.event_kind == "review", Observation.lifecycle == "ended"
            )
        )
        object_observation = await session.scalar(
            select(Observation).where(Observation.event_kind == "object")
        )
        assert review is not None and ended is not None and object_observation is not None
        review_id, observation_id, object_id = review.id, ended.id, object_observation.id

    app = create_app(factory)
    headers = {"Authorization": "Bearer processor-secret"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        claimed = await client.get("/api/v1/processor/jobs/next", headers=headers)
        assert claimed.status_code == 200
        job = claimed.json()
        evidence_id = job["evidence_refs"][0]["evidence_id"]
        now = datetime.now(UTC)
        result = EnrichmentResult(
            job_id=job["job_id"],
            idempotency_key=job["idempotency_key"],
            contract_version="1.0",
            status=ResultStatus.SUCCEEDED,
            model_invocation=ModelInvocationFacts(
                invocation_id=uuid4(),
                provider="video-summary",
                model="caption-tags",
                model_version="1.0",
                outcome=ResultStatus.SUCCEEDED,
                started_at=now - timedelta(seconds=1),
                completed_at=now,
                privacy_route=PrivacyRoute.LOCAL_ONLY,
                external_network_used=False,
            ),
            claims=(
                CaptionClaim(
                    claim_type="caption",
                    schema_version="1.0",
                    text="A car entered the driveway.",
                    confidence=0.9,
                    evidence_ids=(evidence_id,),
                ),
                TagsClaim(
                    claim_type="tags",
                    schema_version="1.0",
                    tags=("car", "driveway"),
                    confidence=0.8,
                    evidence_ids=(evidence_id,),
                ),
            ),
            errors=(),
            completed_at=now,
        )
        submitted = await client.post(
            f"/api/v1/processor/jobs/{job['job_id']}/result",
            headers=headers,
            json=result.model_dump(mode="json"),
        )
        assert submitted.status_code == 200

        by_review = await client.get(f"/api/v1/review-items/{review_id}")
        assert by_review.status_code == 200
        body = by_review.json()
        assert body["id"] == str(observation_id)
        assert body["review_item_id"] == str(review_id)
        assert body["lifecycle"] == "ended"
        assert body["site_id"] == "home"
        assert body["camera_timezone"] == "America/Toronto"
        assert len(body["enrichments"]) == 1
        enrichment = body["enrichments"][0]
        assert enrichment["job_id"] == job["job_id"]
        assert enrichment["status"] == "succeeded"
        assert enrichment["invocation"]["provider"] == "video-summary"
        assert enrichment["invocation"]["model"] == "caption-tags"
        assert {claim["predicate"] for claim in enrichment["claims"]} == {"caption", "tags"}
        assert {value for claim in enrichment["claims"] for value in claim["evidence_ids"]} == {
            evidence_id
        }
        assert {claim["id"] for claim in enrichment["claims"]} == set(submitted.json()["claim_ids"])

        by_observation = await client.get(f"/api/v1/events/{observation_id}")
        assert by_observation.status_code == 200
        assert by_observation.json()["review_item_id"] == str(review_id)
        assert (await client.get(f"/api/v1/review-items/{observation_id}")).status_code == 404
        assert (await client.get(f"/api/v1/events/{review_id}")).status_code == 404
        object_detail = await client.get(f"/api/v1/events/{object_id}")
        assert object_detail.status_code == 200
        assert object_detail.json()["review_item_id"] is None
        assert object_detail.json()["enrichments"] == []
        assert (await client.get(f"/api/v1/review-items/{object_id}")).status_code == 404
        assert (await client.get(f"/api/v1/review-items/{uuid4()}")).status_code == 404

    await engine.dispose()
    get_settings.cache_clear()


async def test_legacy_review_mapping_resolves_without_link_row() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory.begin() as session:
        source = SourceInstance(
            source_type="frigate", name="legacy", adapter_version="1.0", capabilities={}
        )
        review = ReviewItem(
            status="ended",
            start_at=now,
            end_at=now,
            labels=["person"],
            zones=[],
            source_revision="2",
        )
        session.add_all((source, review))
        await session.flush()
        repository = ObservationRepository(session)
        older = await repository.add(
            NewObservation(
                source_instance_id=source.id,
                source_namespace="frigate.review",
                source_entity_id="legacy-1",
                source_revision="1",
                dedupe_key="legacy-1:started",
                schema_version="1.0",
                event_kind="review",
                lifecycle="started",
                occurred_at=now - timedelta(seconds=1),
                observed_at=now - timedelta(seconds=1),
            )
        )
        latest = await repository.add(
            NewObservation(
                source_instance_id=source.id,
                source_namespace="frigate.review",
                source_entity_id="legacy-1",
                source_revision="2",
                dedupe_key="legacy-1:ended",
                schema_version="1.0",
                event_kind="review",
                lifecycle="ended",
                occurred_at=now,
                observed_at=now,
            )
        )
        session.add(
            SourceEntityMap(
                source_instance_id=source.id,
                namespace="frigate.review",
                source_entity_id="legacy-1",
                entity_type="review",
                internal_entity_id=review.id,
            )
        )
        review_id, older_id, latest_id = review.id, older.id, latest.id

    app = create_app(factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/review-items/{review_id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(latest_id)
        assert response.json()["review_item_id"] == str(review_id)
        older_response = await client.get(f"/api/v1/events/{older_id}")
        assert older_response.json()["review_item_id"] == str(review_id)

    await engine.dispose()
