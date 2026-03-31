# ── Hephaestus Makefile ──────────────────────────────────────────────────────
.PHONY: install install-dev test lint lint-ruff lint-mypy format serve docker \
        docker-build docker-stop clean help

# Default target
.DEFAULT_GOAL := help

# Python binary (respects venv if active)
PYTHON ?= python
PIP    ?= pip

# Server config
HOST   ?= 0.0.0.0
PORT   ?= 8000

# ── Installation ──────────────────────────────────────────────────────────────

install:          ## Install hephaestus with web extras
	$(PIP) install -e ".[web]"

install-dev:      ## Install all extras (dev + web) for local development
	$(PIP) install -e ".[dev,web]"

# ── Tests ─────────────────────────────────────────────────────────────────────

test:             ## Run pytest test suite
	$(PYTHON) -m pytest tests/ -v --tb=short

test-cov:         ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ -v --tb=short \
		--cov=src/hephaestus \
		--cov-report=term-missing \
		--cov-report=html:htmlcov

# ── Linting ───────────────────────────────────────────────────────────────────

lint: lint-ruff lint-mypy   ## Run all linters

lint-ruff:        ## Run ruff (fast linter + import sorter)
	$(PYTHON) -m ruff check src/ web/ tests/

lint-mypy:        ## Run mypy type checker
	$(PYTHON) -m mypy src/hephaestus --ignore-missing-imports

format:           ## Auto-format code with ruff
	$(PYTHON) -m ruff check --fix src/ web/ tests/
	$(PYTHON) -m ruff format src/ web/ tests/

# ── Dev server ────────────────────────────────────────────────────────────────

serve:            ## Start dev server with hot reload (uvicorn)
	$(PYTHON) -m uvicorn web.app:app \
		--host $(HOST) \
		--port $(PORT) \
		--reload \
		--reload-dir src \
		--reload-dir web \
		--log-level info

serve-prod:       ## Start production server (no reload)
	$(PYTHON) -m uvicorn web.app:app \
		--host $(HOST) \
		--port $(PORT) \
		--workers 2 \
		--log-level info

# ── Docker ────────────────────────────────────────────────────────────────────

docker:           ## Build and start with docker compose (foreground)
	docker compose up --build

docker-build:     ## Build Docker image only
	docker compose build

docker-up:        ## Start services in background
	docker compose up -d --build

docker-stop:      ## Stop running containers
	docker compose down

docker-logs:      ## Tail docker compose logs
	docker compose logs -f

docker-clean:     ## Remove containers, volumes, and built image
	docker compose down -v --rmi local

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:            ## Remove build artifacts, caches, coverage reports
	rm -rf build/ dist/ *.egg-info src/*.egg-info htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true

# ── Release ───────────────────────────────────────────────────────────────────

build-dist:       ## Build wheel and sdist for PyPI
	$(PIP) install --quiet build
	$(PYTHON) -m build

publish-test:     ## Publish to TestPyPI
	$(PIP) install --quiet twine
	$(PYTHON) -m twine upload --repository testpypi dist/*

# ── Help ──────────────────────────────────────────────────────────────────────

help:             ## Show this help message
	@echo ""
	@echo "  ⚒  Hephaestus — The Invention Engine"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
