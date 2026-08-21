import pytest

from app.domain.user_service import DEFAULT_CURRENCY, DEFAULT_TIMEZONE, UserService

pytestmark = pytest.mark.unit


def test_create_user_aplica_padroes_de_timezone_e_moeda() -> None:
    user = UserService().create_user("Alexandre")

    assert user.name == "Alexandre"
    assert user.timezone == DEFAULT_TIMEZONE == "America/Sao_Paulo"
    assert user.currency == DEFAULT_CURRENCY == "BRL"
    assert user.locale == "pt_BR"


def test_create_user_aceita_valores_explicitos() -> None:
    user = UserService().create_user(
        "Maria", timezone="Europe/Lisbon", currency="EUR", locale="pt_PT"
    )

    assert user.timezone == "Europe/Lisbon"
    assert user.currency == "EUR"
    assert user.locale == "pt_PT"
