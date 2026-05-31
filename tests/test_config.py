import sys

from app.core.config import ENV_FILE, settings


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
