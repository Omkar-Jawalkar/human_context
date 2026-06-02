from __future__ import annotations

from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def paginate(
    session: AsyncSession,
    stmt: Select[tuple[T]],
    *,
    page: int,
    page_size: int,
) -> tuple[list[T], int]:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = await session.scalar(count_stmt) or 0

    offset = (page - 1) * page_size
    paginated_stmt = stmt.offset(offset).limit(page_size)
    result = await session.scalars(paginated_stmt)
    return list(result.all()), total
