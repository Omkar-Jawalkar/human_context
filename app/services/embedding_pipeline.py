import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.sync_database import get_sync_session
from app.models.conversation import Conversation
from app.models.embedding import EmbeddingRecord
from app.models.import_job import ImportJob
from app.models.message import Message
from app.services.embedding_service import embedding_service


class EmbeddingPipelineService:
    def embed_import_job(self, import_job_id: uuid.UUID) -> dict:
        stats = {"embeddings_created": 0, "embeddings_skipped": 0}

        with get_sync_session() as session:
            job = session.get(ImportJob, import_job_id)
            if job is None:
                raise ValueError(f"Import job {import_job_id} not found")

            conversation_ids = session.scalars(
                select(Conversation.id).where(Conversation.import_job_id == import_job_id)
            ).all()

            if not conversation_ids:
                return stats

            messages = session.scalars(
                select(Message).where(Message.conversation_id.in_(conversation_ids))
            ).all()

            if not messages:
                return stats

            namespaces = [f"message:{message.id}" for message in messages]
            existing_namespaces = set(
                session.scalars(
                    select(EmbeddingRecord.namespace).where(
                        EmbeddingRecord.namespace.in_(namespaces)
                    )
                ).all()
            )

            pending_messages = [
                message
                for message in messages
                if f"message:{message.id}" not in existing_namespaces
            ]
            stats["embeddings_skipped"] = len(messages) - len(pending_messages)

            if pending_messages:
                contents = [message.content for message in pending_messages]
                if settings.embedding_provider == "openai":
                    embeddings = embedding_service.embed_texts_parallel(contents)
                else:
                    embeddings = embedding_service.embed_texts(contents)

                records = [
                    EmbeddingRecord(
                        namespace=f"message:{message.id}",
                        content=message.content,
                        metadata_={
                            "message_id": str(message.id),
                            "conversation_id": str(message.conversation_id),
                            "sender": message.sender,
                            "import_job_id": str(import_job_id),
                        },
                        embedding=embedding,
                    )
                    for message, embedding in zip(
                        pending_messages, embeddings, strict=True
                    )
                ]
                session.add_all(records)
                stats["embeddings_created"] = len(records)

            merged_stats = {**job.stats, **stats}
            job.stats = merged_stats

        return stats


embedding_pipeline_service = EmbeddingPipelineService()
