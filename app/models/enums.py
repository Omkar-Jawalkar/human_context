import enum


class ImportSource(enum.StrEnum):
    CLAUDE = "claude"


class ImportJobStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatMessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
