import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.persistence.models import Base, Observation, SourceInstance
from nanexus_event_intelligence.replay.bundle import ReplayBundleError, load_replay_bundle
from nanexus_event_intelligence.replay.exporter import ObservationExporter, ReplayExportError

SOURCE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2260")
EVENT_IDS = (
    UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2261"),
    UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2262"),
)
BASE_TIME = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


async def database() -> tuple[object, async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        session.add(
            SourceInstance(
                id=SOURCE_ID,
                source_type="frigate",
                name="replay-test",
                source_version="0.17.1",
                adapter_version="0.3.0",
                capabilities={},
            )
        )
        for event_id, offset, revision in (
            (EVENT_IDS[1], 10, "2"),
            (EVENT_IDS[0], 0, "1"),
        ):
            at = BASE_TIME + timedelta(seconds=offset)
            session.add(
                Observation(
                    id=event_id,
                    source_instance_id=SOURCE_ID,
                    source_namespace="object",
                    source_entity_id="vehicle-1",
                    source_revision=revision,
                    dedupe_key=f"replay:{revision}",
                    schema_version="1.0",
                    event_kind="object",
                    lifecycle="started" if revision == "1" else "ended",
                    occurred_at=at,
                    observed_at=at + timedelta(milliseconds=100),
                    labels=["car"],
                    zones=["entry"],
                    extensions={
                        "safe": True,
                        "password": "must-not-export",
                        "url": "rtsp://user:pass@camera.local/stream",
                    },
                )
            )
    return engine, factory


@pytest.mark.asyncio
async def test_export_is_stably_sorted_and_byte_deterministic(tmp_path: Path) -> None:
    engine, factory = await database()
    first = tmp_path / "first"
    second = tmp_path / "second"
    async with factory() as session:
        first_manifest = await ObservationExporter(session).export(
            source_instance_id=SOURCE_ID,
            output_dir=first,
            exported_at=BASE_TIME,
        )
        second_manifest = await ObservationExporter(session).export(
            source_instance_id=SOURCE_ID,
            output_dir=second,
            exported_at=BASE_TIME,
        )

    assert (first / "events.jsonl").read_bytes() == (second / "events.jsonl").read_bytes()
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    assert first_manifest.bundle_id == second_manifest.bundle_id
    bundle = load_replay_bundle(first)
    assert [record.event.source_revision for record in bundle.records] == ["1", "2"]
    assert bundle.manifest.contains_credentials is False
    assert bundle.manifest.privacy_review_required is True
    assert bundle.records[0].event.extensions["password"] == "[REDACTED]"
    assert "user:pass" not in bundle.records[0].event.extensions["url"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_export_refuses_overwrite_and_invalid_time_range(tmp_path: Path) -> None:
    engine, factory = await database()
    output = tmp_path / "existing"
    output.mkdir()
    async with factory() as session:
        exporter = ObservationExporter(session)
        with pytest.raises(ReplayExportError, match="already exists"):
            await exporter.export(
                source_instance_id=SOURCE_ID, output_dir=output, exported_at=BASE_TIME
            )
        with pytest.raises(ReplayExportError, match="occurred_from"):
            await exporter.export(
                source_instance_id=SOURCE_ID,
                output_dir=tmp_path / "unused",
                exported_at=BASE_TIME,
                occurred_from=BASE_TIME + timedelta(seconds=1),
                occurred_to=BASE_TIME,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_bundle_rejects_whole_file_and_per_event_tampering(tmp_path: Path) -> None:
    engine, factory = await database()
    output = tmp_path / "bundle"
    async with factory() as session:
        await ObservationExporter(session).export(
            source_instance_id=SOURCE_ID, output_dir=output, exported_at=BASE_TIME
        )

    events_path = output / "events.jsonl"
    original = events_path.read_bytes()
    events_path.write_bytes(original.replace(b'"car"', b'"van"', 1))
    with pytest.raises(ReplayBundleError, match="bundle hash"):
        load_replay_bundle(output)

    lines = original.splitlines()
    record = json.loads(lines[0])
    record["event"]["labels"] = ["tampered"]
    lines[0] = json.dumps(record, separators=(",", ":"), sort_keys=True).encode()
    tampered = b"\n".join(lines) + b"\n"
    events_path.write_bytes(tampered)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["events_sha256"] = hashlib.sha256(tampered).hexdigest()
    manifest["bundle_id"] = str(
        uuid5(NAMESPACE_URL, f"nanexus-replay:{SOURCE_ID}:{manifest['events_sha256']}")
    )
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ReplayBundleError, match="event hash"):
        load_replay_bundle(output)
    await engine.dispose()


@pytest.mark.asyncio
async def test_export_marks_limit_truncation(tmp_path: Path) -> None:
    engine, factory = await database()
    output = tmp_path / "limited"
    async with factory() as session:
        manifest = await ObservationExporter(session).export(
            source_instance_id=SOURCE_ID,
            output_dir=output,
            exported_at=BASE_TIME,
            limit=1,
        )
    assert manifest.event_count == 1
    assert manifest.truncated is True
    assert load_replay_bundle(output).manifest.truncated is True
    await engine.dispose()
