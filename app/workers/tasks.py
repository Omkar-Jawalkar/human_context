import time

from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.process_message", bind=True)
def process_message(self, message: str) -> str:
    """Example async task — replace with your own business logic."""
    time.sleep(2)
    return f"Processed: {message}"
