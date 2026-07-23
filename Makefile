#!/usr/bin/env make
# ──────────────────────────────────────────────
# Enterprise RAG Platform — Makefile
# ──────────────────────────────────────────────

.PHONY: help install dev lint format typecheck test coverage clean docker-up docker-down migrate revision db-init

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install --upgrade pip
	pip install -e .

dev: ## Install dev dependencies
	pip install --upgrade pip
	pip install -e ".[dev]"
	pre-commit install

format: ## Format code with black and ruff
	black app/ tests/
	ruff format app/ tests/

lint: ## Lint code with ruff
	ruff check app/ tests/ --fix

typecheck: ## Run mypy type checking
	mypy app/

test: ## Run tests with coverage
	pytest tests/ -v --cov=app --cov-report=term-missing

coverage: ## Run tests with HTML coverage report
	pytest tests/ --cov=app --cov-report=html
	@echo "Coverage report: file://$(PWD)/htmlcov/index.html"

clean: ## Clean build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__
	rm -rf htmlcov coverage .coverage
	rm -rf *.egg-info dist build
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

# ── Docker Commands ──────────────────────────

docker-up: ## Start all services
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

docker-rebuild: ## Rebuild and start services
	docker compose up -d --build

docker-logs: ## Follow logs
	docker compose logs -f

# ── Database Commands ────────────────────────

db-init: ## Initialize the database (create if not exists)
	@echo "Creating database if not exists..."
	@createdb -U rag_user enterprise_rag 2>/dev/null || true

migrate: ## Run alembic migrations
	alembic upgrade head

revision: ## Create a new migration revision (usage: make revision msg="description")
	@read -p "Migration description: " msg; \
	alembic revision --autogenerate -m "$$msg"

rollback: ## Rollback last migration
	alembic downgrade -1

db-reset: ## Reset database (drop all tables and re-migrate)
	alembic downgrade base
	alembic upgrade head

# ── Development ──────────────────────────────

run: ## Run the application server
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level info

shell: ## Open a Python shell with app context
	PYTHONPATH=. python -c "from app.core.config import settings; print('Settings loaded:', settings.ENVIRONMENT)"

# ── Pre-commit ───────────────────────────────

precommit-install: ## Install pre-commit hooks
	pre-commit install

precommit-run: ## Run pre-commit on all files
	pre-commit run --all-files

# ── Security ─────────────────────────────────

secret: ## Generate a secure random secret key
	python -c "import secrets; print(secrets.token_urlsafe(64))"
