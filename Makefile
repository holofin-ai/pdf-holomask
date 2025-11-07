.PHONY: help install run lint format test clean

help:
	@echo "pdf-holomask - Development Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make install    Install dependencies (including dev dependencies)"
	@echo "  make run        Start the development server"
	@echo "  make lint       Run ruff linter"
	@echo "  make format     Format code with ruff"
	@echo "  make test       Run tests with coverage"
	@echo "  make clean      Remove temporary files and caches"

install:
	uv sync --all-extras

run:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	uv run ruff check .

format:
	uv run ruff format .

test:
	uv run pytest tests/ -v --cov=app --cov-report=term-missing

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	rm -rf uploads/* 2>/dev/null || true
	@echo "Cleanup complete!"
