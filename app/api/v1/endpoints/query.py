from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.user import User
from app.schemas.query import QueryRequest, QueryResponse, QuerySourceResponse
from app.services.query_service import query_service

router = APIRouter()


@router.post("", response_model=QueryResponse)
async def query_context(
    body: QueryRequest,
    isDevelopment: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    user = await db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {body.user_id} not found")

    result = await query_service.answer_query(
        db,
        body.query,
        body.user_id,
        is_development=isDevelopment,
    )

    sources = None
    if result.sources is not None:
        sources = [
            QuerySourceResponse(
                content=source.content,
                distance=source.distance,
                message_id=source.message_id,
                conversation_id=source.conversation_id,
                sender=source.sender,
                import_job_id=source.import_job_id,
            )
            for source in result.sources
        ]

    return QueryResponse(answer=result.answer, sources=sources)
