from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import AppError, LLMError
from app.models.chat_message import ChatMessage
from app.models.chat_thread import ChatThread
from app.models.enums import ChatMessageRole
from app.models.user import User
from app.services.context_access_service import (
    context_access_service,
    no_imports_reply,
)
from app.services.llm_service import ContextUserProfile, llm_service
from app.services.rate_limit_service import rate_limit_service
from app.services.search_service import SearchHit, search_service

logger = logging.getLogger(__name__)


@dataclass
class SendMessageResult:
    user_message: ChatMessage
    assistant_message: ChatMessage


def _hits_to_sources(hits: list[SearchHit]) -> list[dict]:
    sources: list[dict] = []
    for hit in hits:
        metadata = hit.record.metadata_ or {}
        sources.append(
            {
                "content": hit.record.content,
                "distance": hit.distance,
                "message_id": metadata.get("message_id"),
                "conversation_id": metadata.get("conversation_id"),
                "sender": metadata.get("sender"),
                "import_job_id": metadata.get("import_job_id"),
            }
        )
    return sources


def _to_context_profile(user: User) -> ContextUserProfile:
    return ContextUserProfile(id=user.id, name=user.name)


class ChatService:
    async def _get_owned_thread(
        self,
        session: AsyncSession,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        load_messages: bool = False,
    ) -> ChatThread | None:
        stmt = select(ChatThread).where(
            ChatThread.id == thread_id,
            ChatThread.user_id == user_id,
        )
        if load_messages:
            stmt = stmt.options(selectinload(ChatThread.messages))
        return await session.scalar(stmt)

    async def create_thread(
        self,
        session: AsyncSession,
        user: User,
        *,
        title: str = "New chat",
        context_user_id: uuid.UUID,
        use_thread_history: bool,
    ) -> ChatThread:
        await context_access_service.assert_can_access_user_context(
            session, user, context_user_id
        )
        thread = ChatThread(
            user_id=user.id,
            context_user_id=context_user_id,
            organization_id=user.organization_id,
            title=title,
            use_thread_history=use_thread_history,
        )
        session.add(thread)
        await session.flush()
        return thread

    async def list_threads(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> list[ChatThread]:
        stmt = (
            select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc())
        )
        result = await session.scalars(stmt)
        return list(result.all())

    async def get_thread(
        self,
        session: AsyncSession,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatThread | None:
        return await self._get_owned_thread(
            session, thread_id, user_id, load_messages=True
        )

    async def update_thread(
        self,
        session: AsyncSession,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        title: str | None = None,
        use_thread_history: bool | None = None,
    ) -> ChatThread | None:
        thread = await self._get_owned_thread(session, thread_id, user_id)
        if thread is None:
            return None

        if title is not None:
            thread.title = title
        if use_thread_history is not None:
            thread.use_thread_history = use_thread_history

        await session.flush()
        return thread

    async def delete_thread(
        self,
        session: AsyncSession,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        thread = await self._get_owned_thread(session, thread_id, user_id)
        if thread is None:
            return False
        await session.delete(thread)
        await session.flush()
        return True

    async def send_message(
        self,
        session: AsyncSession,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
    ) -> SendMessageResult | None:
        if not content.strip():
            raise LLMError("Message must not be empty")

        await rate_limit_service.assert_chat_send_allowed(user_id)

        thread = await self._get_owned_thread(session, thread_id, user_id)
        if thread is None:
            return None

        caller = await session.get(User, user_id)
        if caller is None:
            return None

        context_user = await context_access_service.assert_can_access_user_context(
            session, caller, thread.context_user_id
        )

        next_sequence = await session.scalar(
            select(func.coalesce(func.max(ChatMessage.sequence), 0)).where(
                ChatMessage.thread_id == thread_id
            )
        )
        user_sequence = int(next_sequence or 0) + 1

        user_message = ChatMessage(
            thread_id=thread_id,
            role=ChatMessageRole.USER.value,
            content=content,
            sequence=user_sequence,
        )
        session.add(user_message)
        await session.flush()

        thread_history: list[tuple[str, str]] = []
        if thread.use_thread_history:
            history_stmt = (
                select(ChatMessage)
                .where(
                    ChatMessage.thread_id == thread_id,
                    ChatMessage.sequence < user_sequence,
                )
                .order_by(ChatMessage.sequence.desc())
                .limit(settings.chat_history_limit)
            )
            prior_messages = list((await session.scalars(history_stmt)).all())
            prior_messages.reverse()
            thread_history = [(msg.role, msg.content) for msg in prior_messages]

        context_profile = _to_context_profile(context_user)

        if not await context_access_service.user_has_imported_conversations(
            session, thread.context_user_id
        ):
            assistant_message = ChatMessage(
                thread_id=thread_id,
                role=ChatMessageRole.ASSISTANT.value,
                content=no_imports_reply(context_user.name),
                sequence=user_sequence + 1,
                sources=None,
            )
            session.add(assistant_message)
            thread.updated_at = datetime.now(UTC)
            await session.flush()
            return SendMessageResult(
                user_message=user_message,
                assistant_message=assistant_message,
            )

        try:
            hits = await search_service.search_similar_messages(
                session,
                content,
                thread.context_user_id,
                limit=settings.chat_rag_hit_limit,
            )
        except AppError:
            raise

        rag_contexts = [hit.record.content or "" for hit in hits]

        try:
            assistant_content = await asyncio.to_thread(
                llm_service.generate_chat_reply,
                thread_messages=thread_history,
                user_message=content,
                context_user=context_profile,
                rag_contexts=rag_contexts,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.exception(
                "Unexpected chat reply failure for thread_id=%s user_id=%s",
                thread_id,
                user_id,
            )
            raise LLMError(f"Failed to generate chat reply: {exc}") from exc

        assistant_message = ChatMessage(
            thread_id=thread_id,
            role=ChatMessageRole.ASSISTANT.value,
            content=assistant_content,
            sequence=user_sequence + 1,
            sources=_hits_to_sources(hits) if hits else None,
        )
        session.add(assistant_message)
        thread.updated_at = datetime.now(UTC)
        await session.flush()

        return SendMessageResult(
            user_message=user_message,
            assistant_message=assistant_message,
        )


chat_service = ChatService()
