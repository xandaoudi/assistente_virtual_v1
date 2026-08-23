from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str
    default_timezone: str = "America/Sao_Paulo"
    default_currency: str = "BRL"
    log_level: str = "INFO"

    llm_provider: str = "google"
    llm_model: str = "gemini-2.5-flash"
    google_api_key: str | None = None
    conversation_history_window: int = 20
    """Nº máximo de mensagens (ModelMessage) recarregadas por turno — §3.3.5, T3.5."""

    telegram_mode: str = "polling"
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None

    @model_validator(mode="after")
    def _valida_chave_do_provider(self) -> Self:
        if self.llm_provider == "google" and not self.google_api_key:
            raise ValueError("GOOGLE_API_KEY é obrigatória quando LLM_PROVIDER=google (RNF-08).")
        return self

    @model_validator(mode="after")
    def _valida_telegram_mode(self) -> Self:
        if self.telegram_mode not in {"polling", "webhook"}:
            raise ValueError(
                f"TELEGRAM_MODE={self.telegram_mode!r} inválido. Use 'polling' ou 'webhook'."
            )
        if self.telegram_mode == "webhook" and not self.telegram_webhook_secret:
            raise ValueError(
                "TELEGRAM_WEBHOOK_SECRET é obrigatório quando TELEGRAM_MODE=webhook (T3.7)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
