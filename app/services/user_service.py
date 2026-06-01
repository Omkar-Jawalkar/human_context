from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User
from app.schemas.user import UserCreate, UserRegister, UserSelfUpdate, UserUpdate


class UserService:
    def assert_self_or_super_admin(self, caller: User, target_user_id: uuid.UUID) -> None:
        if caller.id == target_user_id:
            return
        if not caller.super_admin:
            raise AuthorizationError("Not permitted to access this user")

    def assert_not_super_admin_target(self, target: User) -> None:
        if target.super_admin:
            raise AuthorizationError("Cannot modify platform super admin accounts")

    async def get_user(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> User | None:
        return await session.get(User, user_id)

    async def list_users(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID | None = None,
        unassigned_only: bool = False,
    ) -> list[User]:
        stmt = select(User).where(User.super_admin.is_(False))
        if unassigned_only:
            stmt = stmt.where(User.organization_id.is_(None))
        elif organization_id is not None:
            stmt = stmt.where(User.organization_id == organization_id)
        stmt = stmt.order_by(User.created_at)
        result = await session.scalars(stmt)
        return list(result.all())

    async def _email_exists(self, session: AsyncSession, email: str) -> bool:
        stmt = select(User.id).where(User.email == email)
        return await session.scalar(stmt) is not None

    async def register_user(self, session: AsyncSession, data: UserRegister) -> User:
        if await self._email_exists(session, data.email):
            raise ConflictError(f"User with email {data.email} already exists")
        user = User(
            email=data.email,
            name=data.name,
            organization_id=None,
            super_admin=False,
            password_hash=hash_password(data.password),
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError(f"User with email {data.email} already exists") from exc
        return user

    async def create_user(
        self,
        session: AsyncSession,
        caller: User,
        data: UserCreate,
    ) -> User:
        if not caller.super_admin:
            raise AuthorizationError("Super admin access required")
        if await self._email_exists(session, data.email):
            raise ConflictError(f"User with email {data.email} already exists")
        if data.organization_id is not None:
            org = await session.get(Organization, data.organization_id)
            if org is None:
                raise ConflictError(f"Organization {data.organization_id} not found")
        user = User(
            email=data.email,
            name=data.name,
            organization_id=data.organization_id,
            super_admin=False,
            password_hash=hash_password(data.password) if data.password else None,
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError(f"User with email {data.email} already exists") from exc
        return user

    async def update_self(
        self,
        session: AsyncSession,
        caller: User,
        data: UserSelfUpdate,
    ) -> User:
        if data.name is not None:
            caller.name = data.name
        if data.email is not None:
            if await self._email_exists(session, data.email) and data.email != caller.email:
                raise ConflictError(f"User with email {data.email} already exists")
            caller.email = data.email
        if data.password is not None:
            caller.password_hash = hash_password(data.password)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError("Email already in use") from exc
        return caller

    async def update_user(
        self,
        session: AsyncSession,
        caller: User,
        target: User,
        data: UserUpdate,
    ) -> User:
        self.assert_self_or_super_admin(caller, target.id)
        is_self = caller.id == target.id

        if is_self:
            raise AuthorizationError("Use PATCH /users/me to update your own profile")
        if not caller.super_admin:
            raise AuthorizationError("Super admin access required")
        self.assert_not_super_admin_target(target)

        if "organization_id" in data.model_fields_set:
            if data.organization_id is not None:
                org = await session.get(Organization, data.organization_id)
                if org is None:
                    raise ConflictError(f"Organization {data.organization_id} not found")
            target.organization_id = data.organization_id

        if data.name is not None:
            target.name = data.name
        if data.email is not None:
            if await self._email_exists(session, data.email) and data.email != target.email:
                raise ConflictError(f"User with email {data.email} already exists")
            target.email = data.email
        if data.password is not None:
            target.password_hash = hash_password(data.password)

        try:
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError("Email already in use") from exc
        return target

    async def join_organization(
        self,
        session: AsyncSession,
        caller: User,
        organization_id: uuid.UUID,
    ) -> User:
        if caller.super_admin:
            raise AuthorizationError("Super admins cannot join organizations")
        if caller.organization_id is not None:
            raise ConflictError("User is already assigned to an organization")
        org = await session.get(Organization, organization_id)
        if org is None:
            raise ConflictError(f"Organization {organization_id} not found")
        caller.organization_id = organization_id
        await session.flush()
        return caller

    async def delete_user(
        self,
        session: AsyncSession,
        caller: User,
        target: User,
    ) -> None:
        if not caller.super_admin:
            raise AuthorizationError("Super admin access required")
        if target.super_admin:
            raise AuthorizationError("Cannot delete platform super admin accounts")
        try:
            await session.delete(target)
            await session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "Cannot delete user: import jobs or conversations still reference this user"
            ) from exc


user_service = UserService()
