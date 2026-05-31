import uuid

from sqlalchemy import select

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

            for message in messages:
                namespace = f"message:{message.id}"
                existing = session.scalar(
                    select(EmbeddingRecord).where(EmbeddingRecord.namespace == namespace)
                )
                if existing is not None:
                    stats["embeddings_skipped"] += 1
                    continue

                embedding = embedding_service.embed_text(message.content)
                session.add(
                    EmbeddingRecord(
                        namespace=namespace,
                        content=message.content,
                        metadata_={
                            "message_id": str(message.id),
                            "conversation_id": str(message.conversation_id),
                            "sender": message.sender,
                            "import_job_id": str(import_job_id),
                        },
                        embedding=embedding,
                    )
                )
                stats["embeddings_created"] += 1

            merged_stats = {**job.stats, **stats}
            job.stats = merged_stats

        return stats


embedding_pipeline_service = EmbeddingPipelineService()
