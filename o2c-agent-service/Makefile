.PHONY: install test lint build run docker-build clean

install:
	poetry install

test:
	poetry run pytest tests/ -v --cov=src --cov-report=term-missing

lint:
	poetry run ruff check src/ tests/
	poetry run mypy src/

build:
	poetry build

run:
	poetry run uvicorn o2c_agent_service.main:app --reload --host 0.0.0.0 --port 8000

docker-build:
	docker build -t o2c_agent_service:local .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf dist/ .coverage htmlcov/ .mypy_cache/
