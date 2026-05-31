import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import ImportJobStatus, ImportSource
from app.models.import_job import ImportJob
from app.models.organization import Organization
from app.models.user import User
from app.services.import_service import import_service


class ImportApiService:
    async def get_or_create_default_user(self, session: AsyncSession) -> User:
        stmt = select(User).where(User.email == settings.default_user_email)
        user = await session.scalar(stmt)
        if user is not None:
            return user

        organization = Organization(name="Default Organization")
        session.add(organization)
        await session.flush()

        user = User(
            organization_id=organization.id,
            email=settings.default_user_email,
            name="Default User",
        )
        session.add(user)
        await session.flush()
        return user

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
