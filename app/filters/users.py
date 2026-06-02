from __future__ import annotations

import uuid

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, model_validator
from sqlalchemy import Select

from app.models.user import User


class UserListFilters(BaseModel):
    organization_id: uuid.UUID | None = None
    unassigned_only: bool = False
    email: str | None = None

    @model_validator(mode="after")
    def validate_filters(self) -> UserListFilters:
        if self.unassigned_only and self.organization_id is not None:
            raise ValueError(
                "unassigned_only and organization_id are mutually exclusive"
            )
        return self


def user_list_filters(
    organization_id: uuid.UUID | None = Query(default=None),
    unassigned_only: bool = Query(default=False),
    email: str | None = Query(default=None),
) -> UserListFilters:
    try:
        return UserListFilters(
            organization_id=organization_id,
            unassigned_only=unassigned_only,
            email=email,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def apply_user_filters(
    stmt: Select[tuple[User]],
    filters: UserListFilters,
) -> Select[tuple[User]]:
    stmt = stmt.where(User.super_admin.is_(False))
    if filters.unassigned_only:
        stmt = stmt.where(User.organization_id.is_(None))
    elif filters.organization_id is not None:
        stmt = stmt.where(User.organization_id == filters.organization_id)
    if filters.email is not None:
        stmt = stmt.where(User.email.ilike(f"%{filters.email}%"))
    return stmt
