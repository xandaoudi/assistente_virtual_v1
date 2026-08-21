import uuid

import pytest

from app.domain.category_service import CategoryService
from app.domain.enums import TransactionType
from app.repositories.memory import InMemoryCategoryRepository

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_criar_renomear_e_desativar_alteram_o_estado_esperado() -> None:
    service = CategoryService(InMemoryCategoryRepository())
    user_id = uuid.uuid4()

    categoria = await service.create_category(user_id, "Mercado", TransactionType.EXPENSE)
    assert categoria.name == "Mercado"
    assert categoria.type == TransactionType.EXPENSE
    assert categoria.is_active is True

    renomeada = await service.rename_category(user_id, categoria.id, "Super")
    assert renomeada is not None
    assert renomeada.name == "Super"

    desativada = await service.deactivate_category(user_id, categoria.id)
    assert desativada is not None
    assert desativada.is_active is False


@pytest.mark.asyncio
async def test_categorias_de_despesa_e_receita_sao_conjuntos_distintos() -> None:
    service = CategoryService(InMemoryCategoryRepository())
    user_id = uuid.uuid4()

    await service.create_category(user_id, "Mercado", TransactionType.EXPENSE)
    await service.create_category(user_id, "Salário", TransactionType.INCOME)

    despesas = await service.list_categories(user_id, category_type=TransactionType.EXPENSE)
    receitas = await service.list_categories(user_id, category_type=TransactionType.INCOME)

    assert {categoria.name for categoria in despesas} == {"Mercado"}
    assert {categoria.name for categoria in receitas} == {"Salário"}
