from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError
from app.models.conversation import Conversation
from app.models.user import User


def no_imports_reply(context_user_name: str) -> str:
    return (
        f"{context_user_name} has not imported any Claude conversations yet. "
        "Import their chat history first to use context-aware replies."
    )


class ContextAccessService:
    async def assert_can_access_user_context(
        self,
        session: AsyncSession,
        caller: User,
        target_user_id: uuid.UUID,
    ) -> User:
        if caller.id == target_user_id:
            target = await session.get(User, target_user_id)
            if target is None:
                raise AuthorizationError(f"User {target_user_id} not found")
            return target

        target = await session.get(User, target_user_id)
        if target is None:
            raise AuthorizationError(f"User {target_user_id} not found")

        if caller.organization_id is None or target.organization_id is None:
            raise AuthorizationError("Not permitted to access this user's context")

        if caller.organization_id != target.organization_id:
            raise AuthorizationError("Not permitted to access this user's context")

        return target

    async def user_has_imported_conversations(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> bool:
        stmt = select(
            exists().where(Conversation.user_id == user_id)
        )
        return bool(await session.scalar(stmt))


context_access_service = ContextAccessService()
