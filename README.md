# FastAPI Starter

Production-oriented FastAPI template with layered architecture and Celery background workers.

## Stack

| Layer | Choice |
|-------|--------|
| Python | 3.12 (stable) |
| API | FastAPI + Uvicorn |
| Config | pydantic-settings |
| Database | PostgreSQL 16 + [pgvector](https://github.com/pgvector/pgvector) |
| ORM | SQLAlchemy 2 (async) + Alembic |
| Queue / broker | Redis |
| Workers | Celery |
| Monitoring | Flower (dev dashboard) |

## Project layout

```
app/
├── main.py              # FastAPI app factory
├── core/                # Settings, database, shared infrastructure
├── models/              # SQLAlchemy models (embeddings, etc.)
├── api/                 # HTTP layer (routers, deps)
│   └── v1/endpoints/    # Versioned route handlers
├── schemas/             # Pydantic request/response models
├── services/            # Business logic
└── workers/             # Celery app + task definitions
```

Requests flow: **endpoint → service → worker queue**. Endpoints stay thin; services own orchestration; workers run long-running jobs.

## Quick start

### 1. Environment

Requires Python 3.12. With [pyenv](https://github.com/pyenv/pyenv):

```bash
pyenv install 3.12.8   # if needed
pyenv local 3.12.8
```

Run the setup script (creates venv, installs deps, copies `.env`):

```bash
make setup
source .venv/bin/activate
```

### 2. Start infrastructure

```bash
make redis
make postgres
# or: docker compose up -d redis postgres
```

### 3. Run database migrations

```bash
source .venv/bin/activate
make migrate
```

This enables the `vector` extension and creates the `embedding_records` table (with an HNSW index for cosine similarity).

### 4. Run the API

```bash
make dev
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive API docs.

### 5. Run the worker

In a second terminal:

```bash
source .venv/bin/activate
make worker
```

### 6. Celery dashboard (Flower)

In a third terminal (requires Redis and a running worker for live task data):

```bash
source .venv/bin/activate
make flower
```

Open [http://localhost:5555](http://localhost:5555) to monitor workers, active tasks, task history, and queues.

## API usage

All routes under `/api/v1` require JWT authentication except `/api/v1/health` and `/api/v1/auth/login`. Include the token on protected requests:

```bash
Authorization: Bearer <access_token>
```

**Log in** (email + password):

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "your-password"}'
```

Set a user's password in development (after creating the user in the DB):

```python
from app.core.security import hash_password
# UPDATE users SET password_hash = '<hash>' WHERE email = '...'
hash_password("your-password")
```

Configure `JWT_SECRET_KEY` in `.env` (see `.env.example`).

**Enqueue a background task:**

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"message": "hello from queue"}'
```

Response:

```json
{"task_id": "<uuid>", "status": "queued"}
```

**Poll task status:**

```bash
curl http://localhost:8000/api/v1/tasks/<task_id>
```

## Adding new tasks

1. Define the task in `app/workers/tasks.py`:

```python
@celery_app.task(name="app.workers.tasks.my_task")
def my_task(arg: str) -> str:
    ...
    return result
```

2. Call it from a service in `app/services/`:

```python
from app.workers.tasks import my_task

result = my_task.delay("value")
return result.id
```

3. Expose via a new endpoint under `app/api/v1/endpoints/`.

## Embeddings (PostgreSQL + pgvector)

- Docker image: `pgvector/pgvector:pg16` on host port **5433** (avoids clashing with a local Postgres on 5432).
- Extension enabled on first boot via `docker/postgres/init.sql`.
- Model: `app/models/embedding.py` — `EmbeddingRecord` with `namespace`, optional `content`, `metadata` JSONB, and `embedding` column (`vector(n)`).
- Set `EMBEDDING_DIMENSIONS` in `.env` to match your embedding model (default `1536` for many OpenAI models).
- Import embedding uses batched OpenAI requests: `EMBEDDING_BATCH_SIZE` (default `64`) and `EMBEDDING_MAX_PARALLEL_BATCHES` (default `4`) control chunk size and concurrent HTTP batch workers in `EmbeddingPipelineService`.
- Inject `AsyncSession` in endpoints with `Depends(get_db)` from `app/api/deps.py`.

Example insert (in a service):

```python
from app.models.embedding import EmbeddingRecord

record = EmbeddingRecord(
    namespace="docs",
    content="some text",
    metadata_={"source": "readme"},
    embedding=vector_from_your_model,
)
session.add(record)
await session.commit()
```

Similarity search uses pgvector operators, e.g. `ORDER BY embedding <=> :query_vec LIMIT 10` (cosine distance; the HNSW index uses `vector_cosine_ops`).

## Development

```bash
make test    # run tests
make lint    # ruff
```

## Production notes

- Set `DEBUG=false` and configure real `DATABASE_URL` and Redis URLs via environment variables.
- Run multiple worker processes: `celery -A app.workers.celery_app worker --concurrency=4`.
- Use a process manager (systemd, supervisord) or container orchestration for API + workers.
- Run [Flower](https://flower.readthedocs.io/) for Celery monitoring: `make flower` (set `FLOWER_BASIC_AUTH` in production).
