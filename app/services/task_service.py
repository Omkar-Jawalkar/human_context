from celery.result import AsyncResult

from app.schemas.task import TaskStatus, TaskStatusResponse
from app.workers.celery_app import celery_app
from app.workers.tasks import process_message


class TaskService:
    def enqueue_message(self, message: str) -> str:
        result = process_message.delay(message)
        return result.id

    def get_task_status(self, task_id: str) -> TaskStatusResponse:
        result = AsyncResult(task_id, app=celery_app)
        status = TaskStatus(result.status)

        response = TaskStatusResponse(
            task_id=task_id,
            status=status,
        )

        if result.successful():
            response.result = str(result.result)
        elif result.failed():
            response.error = str(result.result)

        return response


task_service = TaskService()
