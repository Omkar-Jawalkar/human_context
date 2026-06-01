import uuid


def test_users_me_without_token_returns_401(api_client):
    response = api_client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_users_me_ok(jwt_settings, auth_headers, override_current_user, api_client):
    user = override_current_user
    response = api_client.get("/api/v1/users/me", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == user.email
    assert body["super_admin"] is False


def test_tenant_cannot_list_users(
    jwt_settings, auth_headers, override_current_user, api_client
):
    response = api_client.get("/api/v1/users", headers=auth_headers)
    assert response.status_code == 403
    assert response.json()["code"] == "authorization_error"


def test_tenant_cannot_admin_create_users(
    jwt_settings, auth_headers, override_current_user, api_client
):
    response = api_client.post(
        "/api/v1/users",
        json={"email": "new@example.com", "name": "New", "password": "secret123"},
        headers=auth_headers,
    )
    assert response.status_code == 403


def test_register_creates_account_and_returns_token(jwt_settings, api_client):
    email = f"register-{uuid.uuid4()}@example.com"
    response = api_client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "New User", "password": "secret123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    me_resp = api_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email
    assert me_resp.json()["organization_id"] is None
    assert me_resp.json()["super_admin"] is False


def test_register_duplicate_email_returns_409(jwt_settings, test_user_with_password, api_client):
    user, password = test_user_with_password
    response = api_client.post(
        "/api/v1/auth/register",
        json={"email": user.email, "name": "Duplicate", "password": password},
    )
    assert response.status_code == 409


def test_tenant_cannot_access_other_user(
    jwt_settings, auth_headers, override_current_user, api_client
):
    other_id = uuid.uuid4()
    response = api_client.get(f"/api/v1/users/{other_id}", headers=auth_headers)
    assert response.status_code == 403


def test_super_admin_can_update_other_user(
    jwt_settings,
    super_admin_auth_headers,
    override_super_admin_user,
    test_user_with_password,
    api_client,
):
    user, _password = test_user_with_password
    response = api_client.patch(
        f"/api/v1/users/{user.id}",
        json={"name": "Updated By Admin"},
        headers=super_admin_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated By Admin"


def test_tenant_join_organization(
    jwt_settings,
    tenant_no_org_auth_headers,
    override_tenant_no_org_user,
    sync_session,
    api_client,
):
    from app.models.organization import Organization

    org = Organization(name="Join Target Org")
    sync_session.add(org)
    sync_session.commit()
    org_id = str(org.id)

    join_resp = api_client.post(
        "/api/v1/users/me/organization",
        json={"organization_id": org_id},
        headers=tenant_no_org_auth_headers,
    )
    assert join_resp.status_code == 200
    assert join_resp.json()["organization_id"] == org_id


def test_tenant_join_organization_when_already_member_returns_409(
    jwt_settings,
    tenant_no_org_auth_headers,
    override_tenant_no_org_user,
    sync_session,
    api_client,
):
    from app.models.organization import Organization

    org = Organization(name="Already Member Org")
    sync_session.add(org)
    sync_session.flush()
    override_tenant_no_org_user.organization_id = org.id
    sync_session.commit()
    org_id = str(org.id)

    response = api_client.post(
        "/api/v1/users/me/organization",
        json={"organization_id": org_id},
        headers=tenant_no_org_auth_headers,
    )
    assert response.status_code == 409


def test_super_admin_cannot_join_organization(
    jwt_settings, super_admin_auth_headers, override_super_admin_user, api_client
):
    response = api_client.post(
        "/api/v1/users/me/organization",
        json={"organization_id": str(uuid.uuid4())},
        headers=super_admin_auth_headers,
    )
    assert response.status_code == 403


def test_super_admin_create_user(
    jwt_settings, super_admin_auth_headers, override_super_admin_user, api_client
):
    email = f"created-{uuid.uuid4()}@example.com"
    create_resp = api_client.post(
        "/api/v1/users",
        json={"email": email, "name": "Created User"},
        headers=super_admin_auth_headers,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["super_admin"] is False
    assert create_resp.json()["organization_id"] is None


def test_super_admin_list_unassigned_users(
    jwt_settings, super_admin_auth_headers, override_super_admin_user, api_client
):
    email = f"unassigned-{uuid.uuid4()}@example.com"
    api_client.post(
        "/api/v1/users",
        json={"email": email, "name": "Unassigned User"},
        headers=super_admin_auth_headers,
    )
    list_resp = api_client.get(
        "/api/v1/users",
        params={"unassigned_only": True},
        headers=super_admin_auth_headers,
    )
    assert list_resp.status_code == 200
    emails = [u["email"] for u in list_resp.json()["items"]]
    assert email in emails


def test_super_admin_assign_organization(
    jwt_settings, super_admin_auth_headers, override_super_admin_user, api_client
):
    org_resp = api_client.post(
        "/api/v1/organizations",
        json={"name": "Assign Org"},
        headers=super_admin_auth_headers,
    )
    assert org_resp.status_code == 201
    org_id = org_resp.json()["id"]

    email = f"assign-{uuid.uuid4()}@example.com"
    create_resp = api_client.post(
        "/api/v1/users",
        json={"email": email, "name": "Assign User", "organization_id": org_id},
        headers=super_admin_auth_headers,
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    list_resp = api_client.get(
        "/api/v1/users",
        params={"organization_id": org_id},
        headers=super_admin_auth_headers,
    )
    assert list_resp.status_code == 200
    assert any(u["id"] == user_id for u in list_resp.json()["items"])


def test_duplicate_email_returns_409(
    jwt_settings,
    super_admin_auth_headers,
    override_super_admin_user,
    test_user_with_password,
    api_client,
):
    user, _password = test_user_with_password
    response = api_client.post(
        "/api/v1/users",
        json={"email": user.email, "name": "Duplicate"},
        headers=super_admin_auth_headers,
    )
    assert response.status_code == 409


def test_super_admin_delete_user(
    jwt_settings, super_admin_auth_headers, override_super_admin_user, api_client
):
    email = f"delete-{uuid.uuid4()}@example.com"
    create_resp = api_client.post(
        "/api/v1/users",
        json={"email": email, "name": "To Delete"},
        headers=super_admin_auth_headers,
    )
    user_id = create_resp.json()["id"]

    delete_resp = api_client.delete(
        f"/api/v1/users/{user_id}",
        headers=super_admin_auth_headers,
    )
    assert delete_resp.status_code == 204

    get_resp = api_client.get(
        f"/api/v1/users/{user_id}",
        headers=super_admin_auth_headers,
    )
    assert get_resp.status_code == 404
