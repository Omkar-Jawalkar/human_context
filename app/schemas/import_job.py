import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ImportJobStatus, ImportSource


class ImportJobStats(BaseModel):
    conversations_count: int = 0
    messages_created: int = 0
    messages_updated: int = 0
    conversations_skipped: int = 0
    embeddings_created: int = 0
    embeddings_skipped: int = 0


class ImportJobResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    source: ImportSource
    status: ImportJobStatus
    file_name: str
    file_hash: str
    stats: ImportJobStats = Field(default_factory=ImportJobStats)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    celery_task_id: str | None = None
    duplicate: bool = False

    model_config = {"from_attributes": True}


from app.schemas.pagination import PaginatedResponse

ImportJobListResponse = PaginatedResponse[ImportJobResponse]
