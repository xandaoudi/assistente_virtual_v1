from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str
    default_timezone: str = "America/Sao_Paulo"
    default_currency: str = "BRL"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
