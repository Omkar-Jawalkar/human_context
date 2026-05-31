import asyncio
import logging
import uuid

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, EmbeddingError, SearchError
from app.models.conversation import Conversation
from app.models.embedding import EmbeddingRecord
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)


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
        if not query.strip():
            raise SearchError("Search query must not be empty")
        if limit < 1:
            raise SearchError("Search limit must be at least 1")

        try:
            query_vec = await asyncio.to_thread(embedding_service.embed_text, query)
        except AppError:
            raise
        except Exception as exc:
            logger.exception("Failed to embed search query")
            raise EmbeddingError(f"Failed to embed search query: {exc}") from exc

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

        try:
            rows = (await db.execute(stmt)).all()
        except SQLAlchemyError as exc:
            logger.exception("Vector search query failed for user_id=%s", user_id)
            raise SearchError(f"Vector search failed: {exc}") from exc

        return [SearchHit(record=row[0], distance=row[1]) for row in rows]


search_service = SearchService()
