.PHONY: setup install dev worker flower redis postgres migrate test lint re-embed prod-human-context

setup:
	bash scripts/setup.sh

install:
	pip install -e ".[dev]"

dev:
	.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	cd "$(CURDIR)" && celery -A app.workers.celery_app worker --loglevel=info

re-embed:
	@test -n "$(JOB_ID)" || (echo "Usage: make re-embed JOB_ID=<import-job-uuid>" && exit 1)
	cd "$(CURDIR)" && python -c "from app.workers.tasks import embed_import_messages; embed_import_messages.delay({}, '$(JOB_ID)')"

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

prod-human-context:
	bash scripts/prod-human-context.sh
