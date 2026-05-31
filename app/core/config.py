from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "human-context"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = (
        "postgresql+asyncpg://human_context:human_context@localhost:5433/human_context"
    )
    embedding_dimensions: int = 1536

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    upload_dir: str = "/tmp/human_context_uploads"
    default_user_email: str = "default@localhost"

    embedding_provider: str = "fake"
    embedding_batch_size: int = 64
    embedding_max_parallel_batches: int = 4
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"


settings = Settings()
