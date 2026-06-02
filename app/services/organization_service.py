from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError
from app.core.listing import paginate
from app.filters.organizations import OrganizationListFilters, apply_organization_filters
from app.models.import_job import ImportJob
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationUpdate
from app.schemas.pagination import PaginationParams


class OrganizationService:
    def _assert_super_admin(self, caller: User) -> None:
        if not caller.super_admin:
            raise AuthorizationError("Super admin access required")

    async def list_organizations(
        self,
        session: AsyncSession,
        filters: OrganizationListFilters,
        pagination: PaginationParams,
    ) -> tuple[list[Organization], int]:
        stmt = select(Organization).order_by(Organization.created_at)
        stmt = apply_organization_filters(stmt, filters)
        return await paginate(
            session,
            stmt,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_organization(
        self, session: AsyncSession, organization_id: uuid.UUID
    ) -> Organization | None:
        return await session.get(Organization, organization_id)

    async def create_organization(
        self,
        session: AsyncSession,
        caller: User,
        data: OrganizationCreate,
    ) -> Organization:
        self._assert_super_admin(caller)
        org = Organization(name=data.name, meta=data.meta)
        session.add(org)
        await session.flush()
        return org

    async def update_organization(
        self,
        session: AsyncSession,
        caller: User,
        org: Organization,
        data: OrganizationUpdate,
    ) -> Organization:
        self._assert_super_admin(caller)
        if data.name is not None:
            org.name = data.name
        if data.meta is not None:
            org.meta = data.meta
        await session.flush()
        return org

    async def delete_organization(
        self,
        session: AsyncSession,
        caller: User,
        org: Organization,
    ) -> None:
        self._assert_super_admin(caller)
        user_count = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == org.id)
        )
        if user_count:
            raise ConflictError(
                "Cannot delete organization: users are still assigned to it"
            )
        job_count = await session.scalar(
            select(func.count())
            .select_from(ImportJob)
            .where(ImportJob.organization_id == org.id)
        )
        if job_count:
            raise ConflictError(
                "Cannot delete organization: import jobs still reference it"
            )
        try:
            await session.delete(org)
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "Cannot delete organization: related records still reference it"
            ) from exc


organization_service = OrganizationService()
