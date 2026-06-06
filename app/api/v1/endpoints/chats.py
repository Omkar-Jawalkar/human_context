import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.chat_message import ChatMessage
from app.models.chat_thread import ChatThread
from app.models.user import User
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSendMessageResponse,
    ChatSourceResponse,
    ChatThreadCreate,
    ChatThreadListResponse,
    ChatThreadResponse,
    ChatThreadUpdate,
)
from app.services.chat_service import chat_service

router = APIRouter()


def _message_to_response(message: ChatMessage) -> ChatMessageResponse:
    sources = None
    if message.sources:
        sources = [ChatSourceResponse.model_validate(source) for source in message.sources]
    return ChatMessageResponse(
        id=message.id,
        thread_id=message.thread_id,
        role=message.role,
        content=message.content,
        sequence=message.sequence,
        sources=sources,
        created_at=message.created_at,
    )


def _thread_to_response(
    thread: ChatThread, *, include_messages: bool = False
) -> ChatThreadResponse:
    messages: list[ChatMessageResponse] = []
    if include_messages:
        messages = [_message_to_response(message) for message in thread.messages]
    return ChatThreadResponse(
        id=thread.id,
        user_id=thread.user_id,
        context_user_id=thread.context_user_id,
        organization_id=thread.organization_id,
        title=thread.title,
        use_thread_history=thread.use_thread_history,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=messages,
    )


@router.post("", response_model=ChatThreadResponse, status_code=201)
async def create_chat_thread(
    body: ChatThreadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatThreadResponse:
    thread = await chat_service.create_thread(
        db,
        current_user,
        title=body.title,
        context_user_id=body.context_user_id,
        use_thread_history=body.use_thread_history,
    )
    await db.commit()
    await db.refresh(thread)
    return _thread_to_response(thread)


@router.get("", response_model=ChatThreadListResponse)
async def list_chat_threads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatThreadListResponse:
    threads = await chat_service.list_threads(db, current_user.id)
    return ChatThreadListResponse(
        threads=[_thread_to_response(thread) for thread in threads]
    )


@router.get("/{thread_id}", response_model=ChatThreadResponse)
async def get_chat_thread(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatThreadResponse:
    thread = await chat_service.get_thread(db, thread_id, current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Chat thread {thread_id} not found")
    return _thread_to_response(thread, include_messages=True)


@router.patch("/{thread_id}", response_model=ChatThreadResponse)
async def update_chat_thread(
    thread_id: uuid.UUID,
    body: ChatThreadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatThreadResponse:
    thread = await chat_service.update_thread(
        db,
        thread_id,
        current_user.id,
        title=body.title,
        use_thread_history=body.use_thread_history,
    )
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Chat thread {thread_id} not found")
    await db.commit()
    await db.refresh(thread)
    return _thread_to_response(thread)


@router.delete("/{thread_id}", status_code=204)
async def delete_chat_thread(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = await chat_service.delete_thread(db, thread_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Chat thread {thread_id} not found")
    await db.commit()


@router.post("/{thread_id}/messages", response_model=ChatSendMessageResponse)
async def send_chat_message(
    thread_id: uuid.UUID,
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSendMessageResponse:
    result = await chat_service.send_message(
        db, thread_id, current_user.id, body.content
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Chat thread {thread_id} not found")

    await db.commit()
    await db.refresh(result.user_message)
    await db.refresh(result.assistant_message)

    return ChatSendMessageResponse(
        user_message=_message_to_response(result.user_message),
        assistant_message=_message_to_response(result.assistant_message),
    )
