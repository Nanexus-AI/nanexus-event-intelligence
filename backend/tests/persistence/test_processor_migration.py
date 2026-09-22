from pathlib import Path

from alembic.config import Config
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect

from alembic import command
from nanexus_event_intelligence.config import get_settings

PUBLIC_BASE = "ff7f74e1aa8b"
PROCESSOR_REVISION = "a7c2d9e41f10"


def alembic_config(database_url: str) -> Config:
    backend = Path(__file__).resolve().parents[2]
    config = Config(backend / "alembic.ini")
    config.set_main_option("script_location", str(backend / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def column_names(inspector: object, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}  # type: ignore[attr-defined]


def test_processor_migration_upgrades_and_downgrades_public_schema(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    database = tmp_path / "migration.sqlite3"
    sync_url = f"sqlite:///{database}"
    async_url = f"sqlite+aiosqlite:///{database}"
    monkeypatch.setenv("DATABASE_URL", async_url)
    get_settings.cache_clear()
    config = alembic_config(async_url)

    command.upgrade(config, PUBLIC_BASE)
    engine = create_engine(sync_url)
    with engine.connect() as connection:
        before = inspect(connection)
        assert "processor_jobs" not in before.get_table_names()
        review_columns = column_names(before, "review_items")
        invocation_columns = column_names(before, "model_invocations")
        claim_columns = column_names(before, "claims")

    command.upgrade(config, PROCESSOR_REVISION)
    with engine.connect() as connection:
        upgraded = inspect(connection)
        assert "processor_jobs" in upgraded.get_table_names()
        assert "source_revision" in column_names(upgraded, "review_items")
        assert "processor_job_id" in column_names(upgraded, "model_invocations")
        assert "review_item_id" in column_names(upgraded, "claims")
        assert any(
            item["name"] == "uq_processor_jobs_idempotency_key"
            for item in upgraded.get_unique_constraints("processor_jobs")
        )
        assert any(
            item["name"] == "ix_processor_jobs_status_available"
            for item in upgraded.get_indexes("processor_jobs")
        )

    command.downgrade(config, PUBLIC_BASE)
    with engine.connect() as connection:
        downgraded = inspect(connection)
        assert "processor_jobs" not in downgraded.get_table_names()
        assert column_names(downgraded, "review_items") == review_columns
        assert column_names(downgraded, "model_invocations") == invocation_columns
        assert column_names(downgraded, "claims") == claim_columns
    engine.dispose()
    get_settings.cache_clear()
