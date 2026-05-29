.DEFAULT_GOAL := help

PYTHON ?= python3
UV ?= uv

.PHONY: help
help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install/sync workspace dependencies via uv.
	$(UV) sync --all-packages

.PHONY: check
check: lint typecheck ## Run lint and type-check.

.PHONY: lint
lint: ## Run ruff lint and format check.
	$(UV) run ruff check .
	$(UV) run ruff format --check .

.PHONY: format
format: ## Auto-fix lint issues and reformat.
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

.PHONY: typecheck
typecheck: ## Run mypy --strict over the workspace.
	$(UV) run mypy .

.PHONY: hooks
hooks: ## Install pre-commit git hooks.
	$(UV) run pre-commit install

.PHONY: precommit
precommit: ## Run pre-commit on all files.
	$(UV) run pre-commit run --all-files

.PHONY: test
test: ## Run all workspace tests with pytest.
	$(UV) run pytest

.PHONY: migrate
migrate: ## Apply all chat-service migrations to local Postgres.
	cd chat-service && $(UV) run alembic upgrade head

.PHONY: migrate-down
migrate-down: ## Roll back all chat-service migrations (destructive).
	cd chat-service && $(UV) run alembic downgrade base

COMPOSE ?= docker compose

.PHONY: up
up: ## Bring up local infra (Postgres, Redis, MinIO).
	$(COMPOSE) up -d
	@echo "Waiting for services to be healthy..."
	@$(COMPOSE) ps

.PHONY: up-analytics
up-analytics: ## Bring up local infra + ClickHouse (Phase 7+).
	$(COMPOSE) --profile analytics up -d

.PHONY: down
down: ## Tear down local infra (keeps volumes).
	$(COMPOSE) down

.PHONY: down-volumes
down-volumes: ## Tear down local infra AND delete volumes (destructive).
	$(COMPOSE) down --volumes

.PHONY: ps
ps: ## Show container status.
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail logs from all infra containers.
	$(COMPOSE) logs -f

.PHONY: clean
clean: ## Remove Python build/test caches.
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -prune -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -prune -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -prune -exec rm -rf {} +
	rm -rf .uv-cache .coverage htmlcov coverage.xml
