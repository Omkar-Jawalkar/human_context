from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, verify_password
from app.models.user import User


class AuthService:
    async def authenticate_user(
        self,
        db: AsyncSession,
        email: str,
        password: str,
    ) -> User:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None or user.password_hash is None:
            raise AuthenticationError("Invalid email or password")
        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")
        return user

    def create_token_for_user(self, user: User) -> str:
        return create_access_token(user.id)


auth_service = AuthService()
