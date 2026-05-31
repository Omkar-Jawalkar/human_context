import pytest

from app.services.import_service import import_service


def test_compute_file_hash_is_stable():
    data = b"same-content"
    assert import_service.compute_file_hash(data) == import_service.compute_file_hash(data)


@pytest.mark.usefixtures("sync_session")
def test_upsert_conversation_is_idempotent(sync_session, sample_import_setup):
    user, job, parsed = sample_import_setup

    _, created_first, updated_first = import_service.upsert_conversation(
        sync_session,
        user=user,
        import_job=job,
        parsed=parsed,
        account_id="default",
    )
    sync_session.commit()

    _, created_second, updated_second = import_service.upsert_conversation(
        sync_session,
        user=user,
        import_job=job,
        parsed=parsed,
        account_id="default",
    )
    sync_session.commit()

    assert created_first == 2
    assert updated_first == 0
    assert created_second == 0
    assert updated_second == 2
