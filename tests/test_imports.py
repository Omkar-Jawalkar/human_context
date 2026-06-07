import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.models.enums import ImportJobStatus, ImportSource
from app.models.import_job import ImportJob
from app.models.organization import Organization
from app.models.user import User


def _create_import_job(
    sync_session,
    *,
    user: User,
    file_name: str,
    file_hash: str | None = None,
    created_at: datetime | None = None,
    status: ImportJobStatus = ImportJobStatus.PENDING,
) -> ImportJob:
    job = ImportJob(
        user_id=user.id,
        organization_id=user.organization_id,
        source=ImportSource.CLAUDE.value,
        status=status.value,
        file_name=file_name,
        file_hash=file_hash or uuid.uuid4().hex,
    )
    if created_at is not None:
        job.created_at = created_at
    sync_session.add(job)
    sync_session.flush()
    return job


def test_list_imports_without_token_returns_401(api_client):
    response = api_client.get("/api/v1/imports")
    assert response.status_code == 401


def test_list_imports_returns_only_caller_jobs(
    jwt_settings,
    auth_headers,
    override_current_user,
    test_user_with_password,
    sync_session,
    api_client,
):
    caller, _password = test_user_with_password
    base_time = datetime(2026, 1, 1, tzinfo=UTC)

    older_job = _create_import_job(
        sync_session,
        user=caller,
        file_name="older.json",
        created_at=base_time,
    )
    newer_job = _create_import_job(
        sync_session,
        user=caller,
        file_name="newer.json",
        created_at=base_time + timedelta(hours=1),
    )

    other_org = Organization(name="Other Org")
    sync_session.add(other_org)
    sync_session.flush()
    other_user = User(
        organization_id=other_org.id,
        email=f"other-{uuid.uuid4()}@example.com",
        name="Other User",
    )
    sync_session.add(other_user)
    sync_session.flush()
    _create_import_job(sync_session, user=other_user, file_name="other.json")
    sync_session.commit()

    response = api_client.get("/api/v1/imports", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 2
    assert body["total_pages"] == 1
    assert len(body["items"]) == 2
    assert {item["id"] for item in body["items"]} == {
        str(older_job.id),
        str(newer_job.id),
    }
    assert body["items"][0]["file_name"] == "newer.json"
    assert body["items"][1]["file_name"] == "older.json"


def test_get_import_job_returns_own_job(
    jwt_settings,
    auth_headers,
    override_current_user,
    test_user_with_password,
    sync_session,
    api_client,
):
    caller, _password = test_user_with_password
    job = _create_import_job(sync_session, user=caller, file_name="mine.json")
    sync_session.commit()

    response = api_client.get(f"/api/v1/imports/{job.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(job.id)
    assert response.json()["file_name"] == "mine.json"


def test_get_import_job_other_user_returns_404(
    jwt_settings,
    auth_headers,
    override_current_user,
    sync_session,
    api_client,
):
    other_org = Organization(name="Other Org")
    sync_session.add(other_org)
    sync_session.flush()
    other_user = User(
        organization_id=other_org.id,
        email=f"other-{uuid.uuid4()}@example.com",
        name="Other User",
    )
    sync_session.add(other_user)
    sync_session.flush()
    job = _create_import_job(sync_session, user=other_user, file_name="other.json")
    sync_session.commit()

    response = api_client.get(f"/api/v1/imports/{job.id}", headers=auth_headers)
    assert response.status_code == 404


@patch("app.api.v1.endpoints.imports.enqueue_claude_import", return_value="task-123")
def test_upload_import_binds_to_caller(
    mock_enqueue,
    jwt_settings,
    auth_headers,
    override_current_user,
    test_user_with_password,
    api_client,
):
    caller, _password = test_user_with_password
    file_content = b'[{"uuid": "x", "name": "Test", "chat_messages": []}]'

    response = api_client.post(
        "/api/v1/imports",
        headers=auth_headers,
        files={"file": ("conversations.json", file_content, "application/json")},
        data={"account_id": "default"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["user_id"] == str(caller.id)
    assert body["organization_id"] == str(caller.organization_id)
    assert body["file_name"] == "conversations.json"
    assert body["celery_task_id"] == "task-123"
    mock_enqueue.assert_called_once()


@patch("app.api.v1.endpoints.imports.enqueue_claude_import", return_value="task-123")
def test_upload_ignores_user_id_form_param(
    mock_enqueue,
    jwt_settings,
    auth_headers,
    override_current_user,
    test_user_with_password,
    api_client,
):
    caller, _password = test_user_with_password
    other_user_id = uuid.uuid4()
    file_content = b'[{"uuid": "y", "name": "Other", "chat_messages": []}]'

    response = api_client.post(
        "/api/v1/imports",
        headers=auth_headers,
        files={"file": ("other.json", file_content, "application/json")},
        data={"account_id": "default", "user_id": str(other_user_id)},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["user_id"] == str(caller.id)
    assert body["user_id"] != str(other_user_id)
    mock_enqueue.assert_called_once()
