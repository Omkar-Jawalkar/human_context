from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1.endpoints import auth, chats, health, imports, organizations, query, tasks, users

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

protected_router = APIRouter(dependencies=[Depends(get_current_user)])
protected_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
protected_router.include_router(imports.router, prefix="/imports", tags=["imports"])
protected_router.include_router(query.router, prefix="/query", tags=["query"])
protected_router.include_router(chats.router, prefix="/chats", tags=["chats"])
protected_router.include_router(users.router, prefix="/users", tags=["users"])
protected_router.include_router(
    organizations.router, prefix="/organizations", tags=["organizations"]
)
api_router.include_router(protected_router)
