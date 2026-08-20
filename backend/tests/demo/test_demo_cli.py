from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nanexus_event_intelligence.adapters.frigate.demo_cli import seed
from nanexus_event_intelligence.persistence.models import Base, Observation

FIXTURE = Path(__file__).parents[3] / "fixtures/frigate/0.17/vehicle-lifecycle"


async def test_demo_seed_is_repeatable_and_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    source_id, first = await seed(factory, FIXTURE)
    repeated_source_id, second = await seed(factory, FIXTURE)

    assert repeated_source_id == source_id
    assert first == {"persisted": 6, "duplicate": 0, "quarantined": 0, "ignored": 0}
    assert second == {"persisted": 0, "duplicate": 0, "quarantined": 0, "ignored": 0}
    async with factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Observation)
            .where(Observation.source_instance_id == source_id)
        )
        assert count == 6
    await engine.dispose()
