import uuid

from celery import chain

from app.services.embedding_pipeline import embedding_pipeline_service
from app.services.import_service import import_service
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.process_message", bind=True)
def process_message(self, message: str) -> str:
    """Example async task — replace with your own business logic."""
    import time

    time.sleep(2)
    return f"Processed: {message}"


@celery_app.task(name="app.workers.tasks.process_claude_import", bind=True)
def process_claude_import(self, import_job_id: str, account_id: str = "default") -> dict:
    return import_service.process_import_job(uuid.UUID(import_job_id), account_id=account_id)


@celery_app.task(name="app.workers.tasks.embed_import_messages", bind=True)
def embed_import_messages(self, _import_stats: dict, import_job_id: str) -> dict:
    return embedding_pipeline_service.embed_import_job(uuid.UUID(import_job_id))


def enqueue_claude_import(import_job_id: uuid.UUID, account_id: str = "default") -> str:
    workflow = chain(
        process_claude_import.s(str(import_job_id), account_id),
        embed_import_messages.s(str(import_job_id)),
    )
    result = workflow.apply_async()
    return result.id
