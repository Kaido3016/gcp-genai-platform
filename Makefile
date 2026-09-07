.PHONY: install install-gcp dev test test-cov lint format typecheck evaluate build docker-run clean

install:
	pip install -r requirements-dev.txt

install-gcp:
	pip install -r requirements-gcp.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

test:
	pytest tests/unit tests/integration -v

test-cov:
	pytest tests/unit tests/integration --cov=app --cov-report=term-missing

lint:
	ruff check app tests

format:
	ruff format app tests

typecheck:
	mypy app

evaluate:
	python -m evaluation.run_evaluation

build:
	docker build -t gcp-genai-platform:local .

docker-run: build
	docker run --rm -p 8080:8080 --env-file .env gcp-genai-platform:local

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
