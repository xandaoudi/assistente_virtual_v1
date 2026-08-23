import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.unit
def test_defaults_brasileiros(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-de-teste")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")

    settings = Settings(_env_file=None)

    assert settings.default_timezone == "America/Sao_Paulo"
    assert settings.default_currency == "BRL"


@pytest.mark.unit
def test_database_url_ausente_levanta_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-de-teste")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.unit
def test_variavel_de_ambiente_sobrescreve_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-de-teste")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("DEFAULT_CURRENCY", "USD")

    settings = Settings(_env_file=None)

    assert settings.default_currency == "USD"


@pytest.mark.unit
def test_llm_model_ausente_levanta_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # RNF-08: qual modelo usar é sempre configuração — sem valor padrão escondido que
    # possa ficar desatualizado (ou desativado pelo provider) sem ninguém perceber.
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-de-teste")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(ValidationError, match="llm_model"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_google_api_key_ausente_falha_no_start_com_provider_google(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="GOOGLE_API_KEY"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_telegram_mode_padrao_e_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-de-teste")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")
    monkeypatch.delenv("TELEGRAM_MODE", raising=False)

    settings = Settings(_env_file=None)

    assert settings.telegram_mode == "polling"


@pytest.mark.unit
def test_telegram_mode_webhook_e_aceito(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-de-teste")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("TELEGRAM_MODE", "webhook")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "segredo-de-teste")

    settings = Settings(_env_file=None)

    assert settings.telegram_mode == "webhook"


@pytest.mark.unit
def test_telegram_webhook_secret_ausente_falha_no_start_com_provider_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-de-teste")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("TELEGRAM_MODE", "webhook")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    with pytest.raises(ValidationError, match="TELEGRAM_WEBHOOK_SECRET"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_telegram_mode_invalido_falha_no_start_com_mensagem_clara(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-de-teste")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("TELEGRAM_MODE", "carta-registrada")

    with pytest.raises(ValidationError, match="TELEGRAM_MODE"):
        Settings(_env_file=None)
