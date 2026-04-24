SHELL := /bin/bash

COMPOSE := docker compose

.PHONY: help env up down logs ps api-shell migrate seed test api-build web-build build \
        obs-up obs-down \
        backup backups-list backups-prune restore \
        fmt lint

help:
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)

env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "→ .env created from .env.example — edit secrets before running")

build: ## Build all images (no cache-busting)
	$(COMPOSE) build

api-build: ## Build API image only
	$(COMPOSE) build api

web-build: ## Build Web image only
	$(COMPOSE) build web

up: env ## Start core services (api, web, bot, gmail)
	$(COMPOSE) up -d

down: ## Stop all services
	$(COMPOSE) down

logs: ## Tail logs (all services)
	$(COMPOSE) logs -f

ps: ## Show services
	$(COMPOSE) ps

api-shell: ## Bash into api container
	$(COMPOSE) exec api bash

migrate: ## Run alembic migrations
	$(COMPOSE) exec api alembic upgrade head

seed: ## Seed default data
	$(COMPOSE) exec api python -m scripts.seed

test: ## Run API tests inside a throwaway container
	$(COMPOSE) run --rm --no-deps -e PYTHONPATH=/app/src api pytest -q

api-up-only: env ## Only API + DB (no web, bot, gmail)
	$(COMPOSE) up -d api

obs-up: ## Start Langfuse observability stack
	$(COMPOSE) --profile obs -f docker-compose.yml -f docker-compose.obs.yml up -d

obs-down: ## Stop Langfuse
	$(COMPOSE) --profile obs -f docker-compose.yml -f docker-compose.obs.yml down

backup: ## pg_dump Postgres DB → ./backups/
	@mkdir -p backups
	@curl -fsS -X POST http://127.0.0.1:8000/api/v1/admin/backup | python3 -m json.tool

backups-list: ## List files in ./backups/
	@ls -lh backups/*.dump 2>/dev/null || echo "(no backups yet)"

backups-prune: ## Delete backups older than retention
	@curl -fsS -X POST http://127.0.0.1:8000/api/v1/admin/backups/prune | python3 -m json.tool

fmt: ## Ruff format
	$(COMPOSE) run --rm --no-deps api ruff format src tests

lint: ## Ruff lint
	$(COMPOSE) run --rm --no-deps api ruff check src tests
