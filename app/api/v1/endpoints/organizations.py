import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_super_admin
from app.filters.organizations import OrganizationListFilters, organization_list_filters
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.schemas.pagination import PaginationParams, build_paginated_response
from app.services.organization_service import organization_service

router = APIRouter()


@router.get("", response_model=OrganizationListResponse)
async def list_organizations(
    filters: OrganizationListFilters = Depends(organization_list_filters),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
    # _caller: User = Depends(require_super_admin),
) -> OrganizationListResponse:
    orgs, total = await organization_service.list_organizations(
        db, filters, pagination
    )
    return build_paginated_response(
        [OrganizationResponse.model_validate(o) for o in orgs],
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


@router.post("", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(require_super_admin),
) -> OrganizationResponse:
    org = await organization_service.create_organization(db, caller, body)
    await db.commit()
    await db.refresh(org)
    return OrganizationResponse.model_validate(org)


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _caller: User = Depends(require_super_admin),
) -> OrganizationResponse:
    org = await organization_service.get_organization(db, organization_id)
    if org is None:
        raise HTTPException(
            status_code=404, detail=f"Organization {organization_id} not found"
        )
    return OrganizationResponse.model_validate(org)


@router.patch("/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: uuid.UUID,
    body: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(require_super_admin),
) -> OrganizationResponse:
    org = await organization_service.get_organization(db, organization_id)
    if org is None:
        raise HTTPException(
            status_code=404, detail=f"Organization {organization_id} not found"
        )
    org = await organization_service.update_organization(db, caller, org, body)
    await db.commit()
    await db.refresh(org)
    return OrganizationResponse.model_validate(org)


@router.delete("/{organization_id}", status_code=204)
async def delete_organization(
    organization_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(require_super_admin),
) -> None:
    org = await organization_service.get_organization(db, organization_id)
    if org is None:
        raise HTTPException(
            status_code=404, detail=f"Organization {organization_id} not found"
        )
    await organization_service.delete_organization(db, caller, org)
    await db.commit()
