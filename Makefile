# ─── Banking App — Developer Makefile ────────────────────────────────────────
# Shortcuts for common development tasks.
# Usage: make <target>
# On Windows: install 'make' via 'winget install GnuWin32.Make' or use Git Bash

.PHONY: help install env run test watch test-cov test-docker up down logs clean

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Banking App — Available Commands"
	@echo "  ─────────────────────────────────────────────────────"
	@echo "  make install       Install all Python dependencies"
	@echo "  make env           Generate .env file with crypto keys"
	@echo "  make run           Start the FastAPI server (local)"
	@echo ""
	@echo "  make test          Run the full pytest suite (once)"
	@echo "  make watch         Auto-run tests on every file save"
	@echo "  make test-cov      Run tests with a line-by-line coverage report"
	@echo "  make test-docker   Run tests inside Docker"
	@echo ""
	@echo "  make up            Start app + database with Docker Compose"
	@echo "  make down          Stop all Docker containers"
	@echo "  make logs          Tail live logs from all containers"
	@echo "  make clean         Remove __pycache__ and .pyc files"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt

env:
	python generate_env.py

# ── Development Server ────────────────────────────────────────────────────────
run:
	python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# ── Testing ───────────────────────────────────────────────────────────────────

# Run all 89 tests once with verbose output
test:
	python -m pytest tests/ -v --tb=short

# Auto-run tests whenever any .py file is saved (requires pytest-watch)
# Press Ctrl+C to stop watching
watch:
	ptw tests/ -- --tb=short -q

# Full coverage report — shows which lines are NOT tested
test-cov:
	python -m pytest tests/ --cov=. --cov-report=term-missing --cov-omit="venv/*,tests/*"

# Run tests inside a Docker container (uses in-memory SQLite, no DB needed)
test-docker:
	docker-compose --profile test run --rm test

# ── Docker ────────────────────────────────────────────────────────────────────
up:
	docker-compose up --build -d

down:
	docker-compose down

logs:
	docker-compose logs -f

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.pyo" -delete 2>/dev/null || true
	rm -f banking_test.db coverage.xml .coverage
