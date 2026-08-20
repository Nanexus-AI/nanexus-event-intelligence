import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from nanexus_event_intelligence.replay.bundle import canonical_json, event_digest
from nanexus_event_intelligence.replay.cli import async_main, parse_datetime
from nanexus_event_intelligence.replay.models import ReplayEvent, ReplayManifest, ReplayRecord

RUN_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2270")
BUNDLE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2271")
SOURCE_ID = UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2260")
BASE_TIME = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def write_bundle(path: Path) -> None:
    event = ReplayEvent(
        observation_id=UUID("0198b75e-052b-7d4a-9185-d3ea9c2d2280"),
        source_instance_id=SOURCE_ID,
        source_namespace="object",
        source_entity_id="vehicle-1",
        source_revision="1",
        dedupe_key="event:1",
        schema_version="1.0",
        event_kind="object",
        lifecycle="started",
        occurred_at=BASE_TIME,
        observed_at=BASE_TIME,
        labels=["person"],
        zones=["porch"],
    )
    record = ReplayRecord(sequence=0, event_sha256=event_digest(event), event=event)
    events = canonical_json(record.model_dump(mode="json")) + b"\n"
    events_sha256 = hashlib.sha256(events).hexdigest()
    manifest = ReplayManifest(
        bundle_id=uuid5(NAMESPACE_URL, f"nanexus-replay:{SOURCE_ID}:{events_sha256}"),
        source_instance_id=SOURCE_ID,
        source_type="frigate",
        exported_at=BASE_TIME,
        event_count=1,
        first_occurred_at=BASE_TIME,
        last_occurred_at=BASE_TIME,
        events_sha256=events_sha256,
    )
    path.mkdir()
    (path / "events.jsonl").write_bytes(events)
    (path / "manifest.json").write_bytes(canonical_json(manifest.model_dump(mode="json")))


@pytest.mark.asyncio
async def test_cli_run_is_dry_run_and_reproducible(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    bundle = tmp_path / "bundle"
    write_bundle(bundle)
    arguments = [
        "run",
        str(bundle),
        "--fixed-clock",
        "2030-01-01T00:00:00Z",
        "--run-id",
        str(RUN_ID),
    ]

    await async_main(arguments)
    first = json.loads(capsys.readouterr().out)
    await async_main(arguments)
    second = json.loads(capsys.readouterr().out)

    assert first == second
    assert first["status"] == "dry-run-complete"
    assert first["production_side_effects"] is False
    assert first["event_count"] == 1


def test_cli_datetime_requires_timezone() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="timezone"):
        parse_datetime("2026-08-17T12:00:00")


@pytest.mark.asyncio
async def test_cli_export_uses_database_and_emits_safe_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from nanexus_event_intelligence.persistence.models import Base, Observation, SourceInstance
    from nanexus_event_intelligence.replay import cli

    database_path = tmp_path / "replay.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        session.add(
            SourceInstance(
                id=SOURCE_ID,
                source_type="frigate",
                name="cli-export",
                adapter_version="1.0",
                capabilities={},
            )
        )
        session.add(
            Observation(
                source_instance_id=SOURCE_ID,
                source_namespace="object",
                source_entity_id="vehicle-1",
                source_revision="1",
                dedupe_key="cli:1",
                schema_version="1.0",
                event_kind="object",
                lifecycle="started",
                occurred_at=BASE_TIME,
                observed_at=BASE_TIME,
            )
        )
    await engine.dispose()
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(database_url=database_url))
    output = tmp_path / "exported"

    await async_main(
        [
            "export",
            "--source-id",
            str(SOURCE_ID),
            "--output",
            str(output),
            "--exported-at",
            "2026-08-17T12:00:00Z",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "exported"
    assert summary["event_count"] == 1
    assert summary["truncated"] is False


@pytest.mark.asyncio
async def test_cli_can_evaluate_shadow_alerts_without_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    bundle = tmp_path / "alerts-bundle"
    write_bundle(bundle)
    await async_main(["run", str(bundle), "--run-id", str(RUN_ID), "--evaluate-alerts"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["shadow_outcomes"] == ["escalate"]
    assert len(summary["shadow_decision_sha256"]) == 64
    assert summary["production_side_effects"] is False
