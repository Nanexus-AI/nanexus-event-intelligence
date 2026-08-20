FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock* ./
COPY src ./src
RUN uv sync --frozen --no-dev || uv sync --no-dev
COPY alembic.ini ./
COPY alembic ./alembic

FROM base AS development
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "nanexus_event_intelligence.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS production
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "nanexus_event_intelligence.main:app", "--host", "0.0.0.0", "--port", "8000"]
