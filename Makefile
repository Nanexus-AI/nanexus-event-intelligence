.PHONY: install language-check lint typecheck test check community-artifact-check community-tree-check setup-check db-upgrade db-downgrade db-check dev demo demo-down live-demo live-demo-down down

COMPOSE ?= $(shell if docker compose version >/dev/null 2>&1; then printf "docker compose"; elif docker-compose version >/dev/null 2>&1; then printf "docker-compose"; else printf "docker compose"; fi)

install:
	cd backend && uv sync --all-groups
	cd web && npm ci

language-check:
	python3 scripts/check-source-language.py

lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd web && npm run lint

typecheck:
	cd backend && uv run mypy src
	cd web && npm run typecheck

test:
	cd backend && uv run pytest
	cd web && npm run test

check: language-check lint typecheck test

community-artifact-check:
	cd backend && ./scripts/check_community_artifact.sh

community-tree-check:
	./scripts/check-community-release.sh . --preflight

setup-check:
	@command -v docker >/dev/null 2>&1 || { echo "Docker is required"; exit 1; }
	@test -f .env || { echo "Missing .env; run: cp .env.example .env"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker daemon is not available"; exit 1; }
	@$(COMPOSE) version
	@$(COMPOSE) -f compose.yaml config --quiet
	@echo "Evaluation environment check passed"

db-upgrade:
	cd backend && uv run alembic upgrade head

db-downgrade:
	cd backend && uv run alembic downgrade -1

db-check:
	cd backend && uv run alembic check

dev:
	$(COMPOSE) -f compose.yaml up --build

demo:
	$(COMPOSE) -f compose.yaml -f compose.demo.yaml --profile demo build backend web demo-webhook pipeline-worker demo-runner
	$(COMPOSE) -f compose.yaml -f compose.demo.yaml --profile demo up -d postgres redis demo-webhook
	$(COMPOSE) -f compose.yaml -f compose.demo.yaml --profile demo run --rm -e PYTHONPATH=/app/src backend uv run --no-sync alembic upgrade head
	$(COMPOSE) -f compose.yaml -f compose.demo.yaml --profile demo up -d backend web pipeline-worker
	$(COMPOSE) -f compose.yaml -f compose.demo.yaml --profile demo run --rm demo-runner

demo-down:
	$(COMPOSE) -f compose.yaml -f compose.demo.yaml --profile demo down

live-demo:
	-$(COMPOSE) -f compose.yaml -f compose.demo.yaml --profile demo stop demo-webhook
	$(COMPOSE) -f compose.yaml --profile frigate build backend web pipeline-worker frigate-ingest-worker
	$(COMPOSE) -f compose.yaml --profile frigate up -d postgres redis
	$(COMPOSE) -f compose.yaml --profile frigate run --rm -e PYTHONPATH=/app/src backend uv run --no-sync alembic upgrade head
	$(COMPOSE) -f compose.yaml --profile frigate up -d --force-recreate backend web pipeline-worker frigate-ingest-worker

live-demo-down:
	$(COMPOSE) -f compose.yaml --profile frigate stop frigate-ingest-worker

down:
	$(COMPOSE) -f compose.yaml down
