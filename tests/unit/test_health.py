import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.unit
def test_health_retorna_200_sem_dependencias() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
