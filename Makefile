.PHONY: setup install dev worker flower redis postgres migrate test lint

setup:
	bash scripts/setup.sh

install:
	pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	celery -A app.workers.celery_app worker --loglevel=info

flower:
	celery -A app.workers.celery_app flower --port=5555

redis:
	docker compose up -d redis

postgres:
	docker compose up -d postgres

migrate:
	alembic upgrade head

test:
	pytest

lint:
	ruff check app tests
