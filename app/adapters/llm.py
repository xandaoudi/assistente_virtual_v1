"""Constrói o modelo de LLM a partir da configuração — trocar provider é config, não código (RNF-08)."""

from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.core.config import Settings, get_settings

_PROVIDERS_SUPORTADOS = {"google"}


class UnsupportedLLMProviderError(ValueError):
    """`LLM_PROVIDER` configurado não corresponde a nenhum provider implementado."""


def build_llm_model(settings: Settings | None = None) -> Model:
    settings = settings or get_settings()

    if settings.llm_provider not in _PROVIDERS_SUPORTADOS:
        raise UnsupportedLLMProviderError(
            f"LLM_PROVIDER={settings.llm_provider!r} não é suportado. "
            f"Providers disponíveis: {sorted(_PROVIDERS_SUPORTADOS)}."
        )

    assert settings.google_api_key is not None  # noqa: S101 — garantido pelo validator de Settings
    provider = GoogleProvider(api_key=settings.google_api_key)
    return GoogleModel(settings.llm_model, provider=provider)
