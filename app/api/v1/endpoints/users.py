import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_super_admin, require_tenant_user
from app.core.exceptions import AuthenticationError
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserJoinOrganization,
    UserListResponse,
    UserResponse,
    UserSelfUpdate,
    UserUpdate,
)
from app.services.user_service import user_service

router = APIRouter()


def _to_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


async def _load_user(db: AsyncSession, user: User) -> User:
    loaded = await db.get(User, user.id)
    if loaded is None:
        raise AuthenticationError("User not found")
    return loaded


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return _to_response(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_current_user_profile(
    body: UserSelfUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    user = await user_service.update_self(db, await _load_user(db, current_user), body)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


@router.post("/me/organization", response_model=UserResponse)
async def join_organization(
    body: UserJoinOrganization,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_user),
) -> UserResponse:
    user = await user_service.join_organization(
        db, await _load_user(db, current_user), body.organization_id
    )
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


@router.get("", response_model=UserListResponse)
async def list_users(
    organization_id: uuid.UUID | None = Query(default=None),
    unassigned_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _caller: User = Depends(require_super_admin),
) -> UserListResponse:
    users = await user_service.list_users(
        db,
        organization_id=organization_id,
        unassigned_only=unassigned_only,
    )
    return UserListResponse(items=[_to_response(u) for u in users])


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(require_super_admin),
) -> UserResponse:
    user = await user_service.create_user(db, caller, body)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> UserResponse:
    user_service.assert_self_or_super_admin(caller, user_id)
    user = await user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return _to_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(get_current_user),
) -> UserResponse:
    if caller.id == user_id:
        raise HTTPException(
            status_code=400,
            detail="Use PATCH /users/me to update your own profile",
        )
    target = await user_service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    user = await user_service.update_user(db, caller, target, body)
    await db.commit()
    await db.refresh(user)
    return _to_response(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    caller: User = Depends(require_super_admin),
) -> None:
    target = await user_service.get_user(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    await user_service.delete_user(db, caller, target)
    await db.commit()
