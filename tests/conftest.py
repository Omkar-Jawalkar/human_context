import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.enums import ImportJobStatus, ImportSource
from app.models.import_job import ImportJob
from app.models.organization import Organization
from app.models.user import User
from app.services.claude_parser import parse_conversation

TEST_JWT_SECRET = "test-jwt-secret-key-at-least-32-bytes"


@pytest.fixture(scope="session")
def sync_engine():
    sync_url = settings.database_url.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    return engine


@pytest.fixture
def sync_session(sync_engine):
    session_factory = sessionmaker(bind=sync_engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sample_import_setup(sync_session):
    organization = Organization(name="Test Org")
    sync_session.add(organization)
    sync_session.flush()

    user = User(
        organization_id=organization.id,
        email=f"test-{uuid.uuid4()}@example.com",
        name="Test User",
    )
    sync_session.add(user)
    sync_session.flush()

    job = ImportJob(
        user_id=user.id,
        organization_id=organization.id,
        source=ImportSource.CLAUDE.value,
        status=ImportJobStatus.PENDING.value,
        file_name="conversations.json",
        file_hash=uuid.uuid4().hex,
    )
    sync_session.add(job)
    sync_session.flush()

    parsed = parse_conversation(
        {
            "uuid": f"conv-{uuid.uuid4()}",
            "name": "Sample",
            "chat_messages": [
                {"uuid": "m1", "sender": "human", "text": "Hi"},
                {"uuid": "m2", "sender": "assistant", "text": "Hello"},
            ],
        }
    )
    assert parsed is not None
    return user, job, parsed


@pytest.fixture
def test_user_with_password(sync_session):
    organization = Organization(name="Auth Test Org")
    sync_session.add(organization)
    sync_session.flush()

    password = "secret123"
    user = User(
        organization_id=organization.id,
        email=f"auth-{uuid.uuid4()}@example.com",
        name="Auth User",
        password_hash=hash_password(password),
    )
    sync_session.add(user)
    sync_session.commit()
    return user, password


@pytest.fixture
def auth_headers(test_user_with_password, jwt_settings):
    user, _password = test_user_with_password
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def override_current_user(test_user_with_password):
    from app.api.deps import get_current_user
    from app.main import app

    user, _password = test_user_with_password

    async def _override() -> User:
        return user

    app.dependency_overrides[get_current_user] = _override
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def jwt_settings():
    from unittest.mock import patch

    with patch("app.core.security.settings") as mock_settings:
        mock_settings.jwt_secret_key = TEST_JWT_SECRET
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 60
        yield mock_settings
