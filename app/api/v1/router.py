from fastapi import APIRouter

from app.api.v1.endpoints import health, imports, query, tasks

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(query.router, prefix="/query", tags=["query"])
