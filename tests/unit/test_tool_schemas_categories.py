import pytest
from pydantic import ValidationError

from app.domain.enums import TransactionType
from app.tools.schemas import (
    CategoryView,
    CreateCategoryParams,
    CreateCategoryResult,
    GetUserPreferencesParams,
    ListCategoriesParams,
    UpdateUserPreferencesParams,
    UserPreferencesResult,
)

pytestmark = pytest.mark.unit


def test_list_categories_params_aceita_sem_filtro() -> None:
    params = ListCategoriesParams()
    assert params.type is None


def test_list_categories_params_aceita_filtro_de_tipo() -> None:
    params = ListCategoriesParams(type=TransactionType.INCOME)
    assert params.type == TransactionType.INCOME


def test_list_categories_params_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        ListCategoriesParams(user_id="qualquer")  # type: ignore[call-arg]


def test_category_view_expoe_apenas_nome_e_tipo() -> None:
    campos = set(CategoryView.model_fields)
    assert campos == {"name", "type"}


def test_create_category_params_aceita_entrada_valida() -> None:
    params = CreateCategoryParams(name="Pets", type=TransactionType.EXPENSE)
    assert params.name == "Pets"


def test_create_category_params_rejeita_campo_obrigatorio_ausente() -> None:
    with pytest.raises(ValidationError):
        CreateCategoryParams(name="Pets")  # type: ignore[call-arg]


def test_create_category_result_formato() -> None:
    resultado = CreateCategoryResult(name="Pets", type=TransactionType.EXPENSE)
    assert resultado.name == "Pets"
    assert resultado.type == TransactionType.EXPENSE


def test_get_user_preferences_params_nao_tem_campos() -> None:
    assert GetUserPreferencesParams.model_fields == {}


def test_get_user_preferences_params_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        GetUserPreferencesParams(qualquer="coisa")  # type: ignore[call-arg]


def test_update_user_preferences_params_aceita_edicao_parcial() -> None:
    params = UpdateUserPreferencesParams(timezone="Europe/Lisbon")
    assert params.timezone == "Europe/Lisbon"
    assert params.currency is None
    assert params.locale is None


def test_update_user_preferences_params_rejeita_fuso_inexistente() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        UpdateUserPreferencesParams(timezone="Nao/Existe")


def test_update_user_preferences_params_aceita_fuso_valido() -> None:
    params = UpdateUserPreferencesParams(timezone="America/Sao_Paulo")
    assert params.timezone == "America/Sao_Paulo"


def test_user_preferences_result_formato() -> None:
    resultado = UserPreferencesResult(timezone="America/Sao_Paulo", currency="BRL", locale="pt_BR")
    assert resultado.timezone == "America/Sao_Paulo"
    assert resultado.currency == "BRL"
    assert resultado.locale == "pt_BR"
