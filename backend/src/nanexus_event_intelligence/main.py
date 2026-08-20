from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from nanexus_event_intelligence.adapters.frigate.media_api import create_frigate_media_router
from nanexus_event_intelligence.api.router import api_router
from nanexus_event_intelligence.config import get_settings
from nanexus_event_intelligence.persistence.database import create_engine, create_session_factory


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    engine: AsyncEngine | None = None
    if session_factory is None:
        engine = create_engine(get_settings().database_url)
        session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="Nanexus Event Intelligence", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(create_frigate_media_router(get_settings()))
    return app


app = create_app()
