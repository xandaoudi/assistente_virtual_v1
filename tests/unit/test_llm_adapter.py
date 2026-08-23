import pytest
from pydantic_ai.models.google import GoogleModel

from app.adapters.llm import UnsupportedLLMProviderError, build_llm_model
from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql://user:pass@localhost/db",
        "llm_provider": "google",
        "llm_model": "gemini-2.5-flash",
        "google_api_key": "fake-key-de-teste",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


@pytest.mark.unit
def test_configuracao_valida_produz_o_modelo_esperado_sem_chamada_de_rede() -> None:
    settings = _settings()

    model = build_llm_model(settings)

    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-2.5-flash"
    assert model.system == "google"


@pytest.mark.unit
def test_trocar_llm_provider_muda_o_modelo_construido() -> None:
    modelo_google = build_llm_model(_settings(llm_provider="google"))

    with pytest.raises(UnsupportedLLMProviderError, match="openai"):
        build_llm_model(_settings(llm_provider="openai"))

    assert isinstance(modelo_google, GoogleModel)
