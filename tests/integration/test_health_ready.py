from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import get_engine, get_session_maker
from app.main import app


@pytest.fixture
def _fresh_settings_cache() -> Iterator[None]:
    def _clear() -> None:
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_maker.cache_clear()

    _clear()
    yield
    _clear()


@pytest.mark.integration
def test_health_ready_retorna_200_com_banco_de_pe(_fresh_settings_cache: None) -> None:
    client = TestClient(app)

    response = client.get("/health/ready")

    assert response.status_code == 200


@pytest.mark.integration
def test_health_ready_retorna_503_com_banco_fora(
    monkeypatch: pytest.MonkeyPatch, _fresh_settings_cache: None
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://assistente:assistente@127.0.0.1:1/assistente_virtual"
        "?connect_timeout=1",
    )
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_maker.cache_clear()

    client = TestClient(app)

    ready_response = client.get("/health/ready")
    health_response = client.get("/health")

    assert ready_response.status_code == 503
    assert health_response.status_code == 200
