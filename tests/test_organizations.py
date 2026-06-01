import uuid


def test_organizations_without_token_returns_401(api_client):
    response = api_client.get("/api/v1/organizations")
    assert response.status_code == 401


def test_tenant_cannot_access_organizations(
    jwt_settings, auth_headers, override_current_user, api_client
):
    for method, url, kwargs in [
        ("get", "/api/v1/organizations", {}),
        ("post", "/api/v1/organizations", {"json": {"name": "Forbidden"}}),
        ("get", f"/api/v1/organizations/{uuid.uuid4()}", {}),
        ("patch", f"/api/v1/organizations/{uuid.uuid4()}", {"json": {"name": "X"}}),
        ("delete", f"/api/v1/organizations/{uuid.uuid4()}", {}),
    ]:
        response = getattr(api_client, method)(url, headers=auth_headers, **kwargs)
        assert response.status_code == 403, f"{method} {url} returned {response.status_code}"


def test_super_admin_organization_crud(
    jwt_settings, super_admin_auth_headers, override_super_admin_user, api_client
):
    create_resp = api_client.post(
        "/api/v1/organizations",
        json={"name": "CRUD Org", "meta": {"tier": "test"}},
        headers=super_admin_auth_headers,
    )
    assert create_resp.status_code == 201
    org = create_resp.json()
    org_id = org["id"]
    assert org["name"] == "CRUD Org"
    assert org["meta"] == {"tier": "test"}

    list_resp = api_client.get("/api/v1/organizations", headers=super_admin_auth_headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == org_id for item in list_resp.json()["items"])

    get_resp = api_client.get(
        f"/api/v1/organizations/{org_id}",
        headers=super_admin_auth_headers,
    )
    assert get_resp.status_code == 200

    patch_resp = api_client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"name": "Updated Org", "meta": {"tier": "pro"}},
        headers=super_admin_auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Updated Org"

    delete_resp = api_client.delete(
        f"/api/v1/organizations/{org_id}",
        headers=super_admin_auth_headers,
    )
    assert delete_resp.status_code == 204

    get_after = api_client.get(
        f"/api/v1/organizations/{org_id}",
        headers=super_admin_auth_headers,
    )
    assert get_after.status_code == 404


def test_delete_organization_with_users_returns_409(
    jwt_settings,
    super_admin_auth_headers,
    override_super_admin_user,
    test_user_with_password,
    api_client,
):
    user, _password = test_user_with_password
    org_id = str(user.organization_id)

    delete_resp = api_client.delete(
        f"/api/v1/organizations/{org_id}",
        headers=super_admin_auth_headers,
    )
    assert delete_resp.status_code == 409
    assert delete_resp.json()["code"] == "conflict_error"
