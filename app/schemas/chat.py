import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatThreadCreate(BaseModel):
    title: str = Field(default="New chat", max_length=512)
    context_user_id: uuid.UUID
    use_thread_history: bool


class ChatThreadUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    use_thread_history: bool | None = None


class ChatSourceResponse(BaseModel):
    content: str | None
    distance: float
    message_id: str | None = None
    conversation_id: str | None = None
    sender: str | None = None
    import_job_id: str | None = None


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    role: str
    content: str
    sequence: int
    sources: list[ChatSourceResponse] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatThreadResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    context_user_id: uuid.UUID
    organization_id: uuid.UUID | None
    title: str
    use_thread_history: bool
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChatThreadListResponse(BaseModel):
    threads: list[ChatThreadResponse]


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1)


class ChatSendMessageResponse(BaseModel):
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
