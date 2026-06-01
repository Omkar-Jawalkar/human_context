from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db as _get_db
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token
from app.models.user import User


def get_settings():
    return settings


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login",
    auto_error=True,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in _get_db():
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = decode_access_token(token)
    user = await db.get(User, user_id)
    if user is None:
        raise AuthenticationError("User not found")
    return user


async def require_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.super_admin:
        raise AuthorizationError("Super admin access required")
    return current_user


async def require_tenant_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.super_admin:
        raise AuthorizationError("This action is not available for super admins")
    return current_user
