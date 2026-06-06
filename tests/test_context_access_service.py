import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AuthorizationError
from app.models.organization import Organization
from app.models.user import User
from app.services.context_access_service import ContextAccessService


def _user(
    *,
    organization_id: uuid.UUID | None = None,
    name: str = "User",
) -> User:
    user_id = uuid.uuid4()
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        name=name,
        organization_id=organization_id,
    )


@pytest.mark.asyncio
async def test_self_access_allowed_without_org():
    user = _user(organization_id=None)
    db = AsyncMock()
    db.get = AsyncMock(return_value=user)

    service = ContextAccessService()
    result = await service.assert_can_access_user_context(db, user, user.id)
    assert result.id == user.id


@pytest.mark.asyncio
async def test_same_org_teammate_allowed():
    org_id = uuid.uuid4()
    caller = _user(organization_id=org_id, name="Caller")
    target = _user(organization_id=org_id, name="Target")

    db = AsyncMock()
    db.get = AsyncMock(return_value=target)

    service = ContextAccessService()
    result = await service.assert_can_access_user_context(db, caller, target.id)
    assert result.id == target.id


@pytest.mark.asyncio
async def test_different_org_denied():
    caller = _user(organization_id=uuid.uuid4())
    target = _user(organization_id=uuid.uuid4())

    db = AsyncMock()
    db.get = AsyncMock(return_value=target)

    service = ContextAccessService()
    with pytest.raises(AuthorizationError, match="Not permitted"):
        await service.assert_can_access_user_context(db, caller, target.id)


@pytest.mark.asyncio
async def test_caller_without_org_cannot_access_teammate():
    caller = _user(organization_id=None)
    target = _user(organization_id=uuid.uuid4())

    db = AsyncMock()
    db.get = AsyncMock(return_value=target)

    service = ContextAccessService()
    with pytest.raises(AuthorizationError, match="Not permitted"):
        await service.assert_can_access_user_context(db, caller, target.id)


@pytest.mark.asyncio
async def test_user_has_imported_conversations():
    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[True, False])

    service = ContextAccessService()
    user_id = uuid.uuid4()

    assert await service.user_has_imported_conversations(db, user_id) is True
    assert await service.user_has_imported_conversations(db, user_id) is False
