import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.enums import ImportJobStatus, ImportSource
from app.models.import_job import ImportJob
from app.models.user import User
from app.schemas.import_job import ImportJobResponse, ImportJobStats
from app.services.import_api_service import import_api_service
from app.workers.tasks import enqueue_claude_import

router = APIRouter()


def _to_response(
    job: ImportJob, *, celery_task_id: str | None = None, duplicate: bool = False
) -> ImportJobResponse:
    stats_data = job.stats or {}
    return ImportJobResponse(
        id=job.id,
        user_id=job.user_id,
        organization_id=job.organization_id,
        source=ImportSource(job.source),
        status=ImportJobStatus(job.status),
        file_name=job.file_name,
        file_hash=job.file_hash,
        stats=ImportJobStats(**stats_data),
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        celery_task_id=celery_task_id,
        duplicate=duplicate,
    )


@router.post("", response_model=ImportJobResponse, status_code=202)
async def upload_claude_export(
    file: UploadFile = File(...),
    account_id: str = Form(default="default"),
    user_id: uuid.UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    file_hash = import_api_service.compute_file_hash(data)
    file_name = file.filename or "conversations.json"

    # Default user is created if not provided
    if user_id is None:
        user = await import_api_service.get_or_create_default_user(db)
    else:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    existing = await import_api_service.get_existing_import_job(db, user.id, file_hash)
    if existing is not None:
        await db.commit()
        return _to_response(existing, duplicate=True)

    job = await import_api_service.create_import_job(
        db,
        user=user,
        file_name=file_name,
        file_hash=file_hash,
    )
    await db.commit()

    import_api_service.save_upload(job.id, data)
    celery_task_id = enqueue_claude_import(job.id, account_id=account_id)

    await db.refresh(job)
    return _to_response(job, celery_task_id=celery_task_id)


@router.get("/{import_job_id}", response_model=ImportJobResponse)
async def get_import_job(
    import_job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    job = await db.get(ImportJob, import_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Import job {import_job_id} not found")
    return _to_response(job)
