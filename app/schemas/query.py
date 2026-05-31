import uuid

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    user_id: uuid.UUID


class QuerySourceResponse(BaseModel):
    content: str | None
    distance: float
    message_id: str | None = None
    conversation_id: str | None = None
    sender: str | None = None
    import_job_id: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[QuerySourceResponse] | None = None
