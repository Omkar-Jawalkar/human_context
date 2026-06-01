from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1.endpoints import auth, health, imports, query, tasks

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

protected_router = APIRouter(dependencies=[Depends(get_current_user)])
protected_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
protected_router.include_router(imports.router, prefix="/imports", tags=["imports"])
protected_router.include_router(query.router, prefix="/query", tags=["query"])
api_router.include_router(protected_router)
