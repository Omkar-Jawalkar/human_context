import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.enums import ImportJobStatus, ImportSource
from app.models.import_job import ImportJob
from app.models.organization import Organization
from app.models.user import User
from app.services.claude_parser import parse_conversation


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
