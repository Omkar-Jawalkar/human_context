import asyncio
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, LLMError
from app.services.llm_service import llm_service
from app.services.search_service import SearchHit, search_service

logger = logging.getLogger(__name__)


@dataclass
class QuerySource:
    content: str | None
    distance: float
    message_id: str | None
    conversation_id: str | None
    sender: str | None
    import_job_id: str | None


@dataclass
class QueryResult:
    answer: str
    sources: list[QuerySource] | None


def _hit_to_source(hit: SearchHit) -> QuerySource:
    metadata = hit.record.metadata_ or {}
    return QuerySource(
        content=hit.record.content,
        distance=hit.distance,
        message_id=metadata.get("message_id"),
        conversation_id=metadata.get("conversation_id"),
        sender=metadata.get("sender"),
        import_job_id=metadata.get("import_job_id"),
    )


class QueryService:
    async def answer_query(
        self,
        db: AsyncSession,
        query: str,
        user_id: uuid.UUID,
        *,
        is_development: bool = False,
    ) -> QueryResult:
        if not query.strip():
            raise LLMError("Query must not be empty")

        try:
            hits = await search_service.search_similar_messages(
                db, query, user_id, limit=5
            )
        except AppError:
            raise

        contexts = [hit.record.content or "" for hit in hits]

        try:
            answer = await asyncio.to_thread(
                llm_service.generate_answer, query, contexts
            )
        except AppError:
            raise
        except Exception as exc:
            logger.exception("Unexpected query failure for user_id=%s", user_id)
            raise LLMError(f"Failed to generate answer: {exc}") from exc

        sources = None
        if is_development:
            sources = [_hit_to_source(hit) for hit in hits]

        return QueryResult(answer=answer, sources=sources)


query_service = QueryService()
