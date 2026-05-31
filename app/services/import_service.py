import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.sync_database import get_sync_session
from app.models.conversation import Conversation
from app.models.enums import ImportJobStatus, ImportSource
from app.models.import_job import ImportJob
from app.models.message import Message
from app.models.user import User
from app.services.claude_parser import ParsedConversation, load_conversations_from_bytes


class ImportService:
    def compute_file_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def save_upload(self, import_job_id: uuid.UUID, data: bytes) -> Path:
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / f"{import_job_id}.bin"
        path.write_bytes(data)
        return path

    def load_upload(self, import_job_id: uuid.UUID) -> bytes:
        path = Path(settings.upload_dir) / f"{import_job_id}.bin"
        return path.read_bytes()

    def upsert_conversation(
        self,
        session: Session,
        *,
        user: User,
        import_job: ImportJob,
        parsed: ParsedConversation,
        account_id: str,
    ) -> tuple[Conversation, int, int]:
        source = ImportSource.CLAUDE.value
        stmt = select(Conversation).where(
            Conversation.source == source,
            Conversation.external_uuid == parsed.external_uuid,
            Conversation.account_id == account_id,
        )
        conversation = session.scalar(stmt)
        created_messages = 0
        updated_messages = 0

        if conversation is None:
            conversation = Conversation(
                user_id=user.id,
                organization_id=user.organization_id,
                import_job_id=import_job.id,
                external_uuid=parsed.external_uuid,
                name=parsed.name,
                source=source,
                account_id=account_id,
                meta=parsed.meta,
                source_created_at=parsed.source_created_at,
                source_updated_at=parsed.source_updated_at,
            )
            session.add(conversation)
            session.flush()
        else:
            conversation.name = parsed.name
            conversation.meta = parsed.meta
            conversation.source_created_at = parsed.source_created_at
            conversation.source_updated_at = parsed.source_updated_at
            conversation.import_job_id = import_job.id

        for parsed_message in parsed.messages:
            message_stmt = select(Message).where(
                Message.conversation_id == conversation.id,
                Message.external_uuid == parsed_message.external_uuid,
            )
            message = session.scalar(message_stmt)
            if message is None:
                session.add(
                    Message(
                        conversation_id=conversation.id,
                        external_uuid=parsed_message.external_uuid,
                        sender=parsed_message.sender,
                        content=parsed_message.content,
                        sequence=parsed_message.sequence,
                        source_created_at=parsed_message.source_created_at,
                    )
                )
                created_messages += 1
            else:
                message.sender = parsed_message.sender
                message.content = parsed_message.content
                message.sequence = parsed_message.sequence
                message.source_created_at = parsed_message.source_created_at
                updated_messages += 1

        return conversation, created_messages, updated_messages

    def process_import_job(self, import_job_id: uuid.UUID, account_id: str = "default") -> dict:
        stats = {
            "conversations_count": 0,
            "messages_created": 0,
            "messages_updated": 0,
            "conversations_skipped": 0,
        }

        with get_sync_session() as session:
            job = session.get(ImportJob, import_job_id)
            if job is None:
                raise ValueError(f"Import job {import_job_id} not found")

            user = session.get(User, job.user_id)
            if user is None:
                raise ValueError(f"User {job.user_id} not found")

            job.status = ImportJobStatus.PROCESSING.value
            job.started_at = datetime.now(UTC)
            job.error_message = None
            session.flush()

            try:
                data = self.load_upload(import_job_id)
                parsed_conversations = load_conversations_from_bytes(data)

                for parsed in parsed_conversations:
                    if not parsed.messages:
                        stats["conversations_skipped"] += 1
                        continue

                    _, created, updated = self.upsert_conversation(
                        session,
                        user=user,
                        import_job=job,
                        parsed=parsed,
                        account_id=account_id,
                    )
                    stats["conversations_count"] += 1
                    stats["messages_created"] += created
                    stats["messages_updated"] += updated

                job.status = ImportJobStatus.COMPLETED.value
                job.completed_at = datetime.now(UTC)
                job.stats = stats
            except Exception as exc:
                job.status = ImportJobStatus.FAILED.value
                job.completed_at = datetime.now(UTC)
                job.error_message = str(exc)
                job.stats = stats
                raise

        return stats


import_service = ImportService()
