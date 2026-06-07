import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import AuthorizationError
from app.models.enums import ImportJobStatus, ImportSource
from app.models.import_job import ImportJob
from app.models.user import User
from app.schemas.import_job import ImportJobListResponse, ImportJobResponse, ImportJobStats
from app.schemas.pagination import PaginationParams, build_paginated_response
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


@router.get("", response_model=ImportJobListResponse)
async def list_import_jobs(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportJobListResponse:
    jobs, total = await import_api_service.list_import_jobs(
        db, current_user.id, pagination
    )
    return build_paginated_response(
        [_to_response(job) for job in jobs],
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


@router.post("", response_model=ImportJobResponse, status_code=202)
async def upload_claude_export(
    file: UploadFile = File(...),
    account_id: str = Form(default="default"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportJobResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    file_hash = import_api_service.compute_file_hash(data)
    file_name = file.filename or "conversations.json"

    if current_user.organization_id is None:
        raise AuthorizationError("User must join an organization before importing")

    existing = await import_api_service.get_existing_import_job(
        db, current_user.id, file_hash
    )
    if existing is not None:
        await db.commit()
        return _to_response(existing, duplicate=True)

    job = await import_api_service.create_import_job(
        db,
        user=current_user,
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
    current_user: User = Depends(get_current_user),
) -> ImportJobResponse:
    job = await import_api_service.get_import_job_for_user(
        db, import_job_id, current_user.id
    )
    if job is None:
        raise HTTPException(status_code=404, detail=f"Import job {import_job_id} not found")
    return _to_response(job)
