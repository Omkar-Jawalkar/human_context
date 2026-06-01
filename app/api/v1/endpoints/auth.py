from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserRegister
from app.services.auth_service import auth_service
from app.services.user_service import user_service

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await user_service.register_user(db, body)
    await db.commit()
    await db.refresh(user)
    access_token = auth_service.create_token_for_user(user)
    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await auth_service.authenticate_user(db, body.email, body.password)
    access_token = auth_service.create_token_for_user(user)
    return TokenResponse(access_token=access_token)
