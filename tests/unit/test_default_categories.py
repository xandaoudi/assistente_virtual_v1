import uuid

import pytest

from app.domain.default_categories import DEFAULT_CATEGORY_NAMES, build_default_categories
from app.domain.enums import TransactionType

pytestmark = pytest.mark.unit

_NOMES_ESPERADOS = {
    "Alimentação",
    "Mercado",
    "Transporte",
    "Moradia",
    "Saúde",
    "Educação",
    "Lazer",
    "Vestuário",
    "Assinaturas",
    "Outros",
}


def test_conjunto_padrao_tem_as_dez_categorias_esperadas() -> None:
    assert len(DEFAULT_CATEGORY_NAMES) == 10
    assert set(DEFAULT_CATEGORY_NAMES) == _NOMES_ESPERADOS


def test_build_default_categories_monta_dez_categorias_de_despesa_do_usuario() -> None:
    user_id = uuid.uuid4()

    categorias = build_default_categories(user_id)

    assert len(categorias) == 10
    assert {categoria.name for categoria in categorias} == _NOMES_ESPERADOS
    assert all(categoria.user_id == user_id for categoria in categorias)
    assert all(categoria.type == TransactionType.EXPENSE for categoria in categorias)
    assert all(categoria.is_default for categoria in categorias)
    assert all(categoria.is_active for categoria in categorias)
