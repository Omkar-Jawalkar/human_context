from fastapi import APIRouter, status

from app.schemas.task import TaskEnqueueRequest, TaskEnqueueResponse, TaskStatusResponse
from app.services.task_service import task_service

router = APIRouter()


@router.post("", response_model=TaskEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_task(payload: TaskEnqueueRequest) -> TaskEnqueueResponse:
    task_id = task_service.enqueue_message(payload.message)
    return TaskEnqueueResponse(task_id=task_id, status="queued")


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    return task_service.get_task_status(task_id)
