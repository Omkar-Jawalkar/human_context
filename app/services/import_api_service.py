import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listing import paginate
from app.models.enums import ImportJobStatus, ImportSource
from app.models.import_job import ImportJob
from app.models.user import User
from app.schemas.pagination import PaginationParams
from app.services.import_service import import_service


class ImportApiService:
    async def list_import_jobs(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        pagination: PaginationParams,
    ) -> tuple[list[ImportJob], int]:
        stmt = (
            select(ImportJob)
            .where(ImportJob.user_id == user_id)
            .order_by(ImportJob.created_at.desc())
        )
        return await paginate(
            session,
            stmt,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_import_job_for_user(
        self,
        session: AsyncSession,
        import_job_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ImportJob | None:
        stmt = select(ImportJob).where(
            ImportJob.id == import_job_id,
            ImportJob.user_id == user_id,
        )
        return await session.scalar(stmt)

    async def get_existing_import_job(
        self, session: AsyncSession, user_id: uuid.UUID, file_hash: str
    ) -> ImportJob | None:
        stmt = select(ImportJob).where(
            ImportJob.user_id == user_id,
            ImportJob.file_hash == file_hash,
        )
        return await session.scalar(stmt)

    async def create_import_job(
        self,
        session: AsyncSession,
        *,
        user: User,
        file_name: str,
        file_hash: str,
        source: ImportSource = ImportSource.CLAUDE,
    ) -> ImportJob:
        job = ImportJob(
            user_id=user.id,
            organization_id=user.organization_id,
            source=source.value,
            status=ImportJobStatus.PENDING.value,
            file_name=file_name,
            file_hash=file_hash,
        )
        session.add(job)
        await session.flush()
        return job

    def compute_file_hash(self, data: bytes) -> str:
        return import_service.compute_file_hash(data)

    def save_upload(self, import_job_id: uuid.UUID, data: bytes) -> None:
        import_service.save_upload(import_job_id, data)


import_api_service = ImportApiService()
