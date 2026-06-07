import sys

from fastapi.testclient import TestClient

from app.core.config import ENV_FILE, Settings, settings


def test_settings_load_openai_from_project_env_file():
    assert ENV_FILE.is_file()
    assert settings.embedding_provider == "openai"
    assert settings.openai_api_key


def test_settings_load_env_file_regardless_of_cwd(monkeypatch):
    monkeypatch.chdir("/")
    for module_name in ("app.core.config", "app.core"):
        sys.modules.pop(module_name, None)

    from app.core.config import settings as reloaded_settings

    assert reloaded_settings.embedding_provider == "openai"
    assert reloaded_settings.openai_api_key


def _reload_settings(monkeypatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("app.core.config", None)
    return Settings()


def test_cors_origins_default_list():
    s = Settings(_env_file=None)
    assert s.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_cors_origins_parses_comma_separated_env(monkeypatch):
    s = _reload_settings(
        monkeypatch,
        CORS_ORIGINS="https://human-context.byomkar.com",
    )
    assert s.cors_origins == ["https://human-context.byomkar.com"]


def test_cors_origins_parses_multiple_comma_separated_values(monkeypatch):
    s = _reload_settings(
        monkeypatch,
        CORS_ORIGINS="https://human-context.byomkar.com,https://www.human-context.byomkar.com",
    )
    assert s.cors_origins == [
        "https://human-context.byomkar.com",
        "https://www.human-context.byomkar.com",
    ]


def test_cors_preflight_allows_configured_origin(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://human-context.byomkar.com",
    )
    monkeypatch.setenv("APP_ENV", "production")
    sys.modules.pop("app.core.config", None)
    sys.modules.pop("app.main", None)

    from app.main import create_app

    client = TestClient(create_app())
    response = client.options(
        "/health",
        headers={
            "Origin": "https://human-context.byomkar.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "https://human-context.byomkar.com"
    )


def test_cors_preflight_rejects_unlisted_origin(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://human-context.byomkar.com",
    )
    monkeypatch.setenv("APP_ENV", "production")
    sys.modules.pop("app.core.config", None)
    sys.modules.pop("app.main", None)

    from app.main import create_app

    client = TestClient(create_app())
    response = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
