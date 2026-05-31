import asyncio
import uuid

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.embedding import EmbeddingRecord
from app.services.embedding_service import embedding_service


class SearchHit:
    def __init__(self, record: EmbeddingRecord, distance: float) -> None:
        self.record = record
        self.distance = distance


class SearchService:
    async def search_similar_messages(
        self,
        db: AsyncSession,
        query: str,
        user_id: uuid.UUID,
        *,
        limit: int = 5,
    ) -> list[SearchHit]:
        query_vec = await asyncio.to_thread(embedding_service.embed_text, query)

        distance = EmbeddingRecord.embedding.cosine_distance(query_vec).label("distance")
        stmt = (
            select(EmbeddingRecord, distance)
            .join(
                Conversation,
                Conversation.id
                == cast(
                    EmbeddingRecord.metadata_["conversation_id"].astext,
                    UUID(as_uuid=True),
                ),
            )
            .where(Conversation.user_id == user_id)
            .order_by(distance)
            .limit(limit)
        )

        rows = (await db.execute(stmt)).all()
        return [SearchHit(record=row[0], distance=row[1]) for row in rows]


search_service = SearchService()
