from __future__ import annotations

from datetime import datetime

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, model_validator
from sqlalchemy import Select

from app.models.organization import Organization


class OrganizationListFilters(BaseModel):
    name: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> OrganizationListFilters:
        if (
            self.created_after is not None
            and self.created_before is not None
            and self.created_after > self.created_before
        ):
            raise ValueError("created_after must be <= created_before")
        return self


def organization_list_filters(
    name: str | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
) -> OrganizationListFilters:
    try:
        return OrganizationListFilters(
            name=name,
            created_after=created_after,
            created_before=created_before,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def apply_organization_filters(
    stmt: Select[tuple[Organization]],
    filters: OrganizationListFilters,
) -> Select[tuple[Organization]]:
    if filters.name is not None:
        stmt = stmt.where(Organization.name.ilike(f"%{filters.name}%"))
    if filters.created_after is not None:
        stmt = stmt.where(Organization.created_at >= filters.created_after)
    if filters.created_before is not None:
        stmt = stmt.where(Organization.created_at <= filters.created_before)
    return stmt
