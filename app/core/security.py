import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConfigurationError


def _require_jwt_secret() -> str:
    if not settings.jwt_secret_key:
        raise ConfigurationError("JWT_SECRET_KEY is required")
    return settings.jwt_secret_key


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    user_id: uuid.UUID,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    secret = _require_jwt_secret()
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    secret = _require_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc

    sub = payload.get("sub")
    if not sub:
        raise AuthenticationError("Invalid token payload")

    try:
        return uuid.UUID(sub)
    except ValueError as exc:
        raise AuthenticationError("Invalid token subject") from exc
