from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql://gully11:gully11@localhost:5432/gully11"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000"]
    # Any localhost port in development (the dev server may move off 3000).
    cors_origin_regex: str | None = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


settings = Settings()
