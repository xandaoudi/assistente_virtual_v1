import uuid
from datetime import date

import pytest

from app.domain.enums import TransactionType
from app.models.user import User
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.results import ErrorCode, ToolError, ToolSuccess
from app.tools.schemas import (
    CreateCategoryParams,
    GetUserPreferencesParams,
    ListCategoriesParams,
    UpdateUserPreferencesParams,
)

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 21)


def _novo_registry() -> tuple[ToolRegistry, InMemoryCategoryRepository, InMemoryUserRepository]:
    categorias = InMemoryCategoryRepository()
    usuarios = InMemoryUserRepository()
    registry = ToolRegistry(
        InMemoryTransactionRepository(), categorias, usuarios, InMemoryToolAuditLogRepository()
    )
    return registry, categorias, usuarios


def _novo_contexto(**overrides: object) -> ToolContext:
    padrao: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "timezone": "America/Sao_Paulo",
        "currency": "BRL",
        "today": _HOJE,
    }
    padrao.update(overrides)
    return ToolContext(**padrao)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_list_categories_devolve_so_categorias_ativas_do_usuario_do_contexto() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()
    outro_ctx = _novo_contexto()

    await registry.create_category(
        ctx, CreateCategoryParams(name="Pets", type=TransactionType.EXPENSE)
    )
    criada = await registry.create_category(
        outro_ctx, CreateCategoryParams(name="Salário", type=TransactionType.INCOME)
    )
    assert isinstance(criada, ToolSuccess)

    resultado = await registry.list_categories(ctx, ListCategoriesParams())

    assert isinstance(resultado, ToolSuccess)
    nomes = {item.name for item in resultado.data}
    assert nomes == {"Pets"}


@pytest.mark.asyncio
async def test_list_categories_filtra_por_tipo() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()
    await registry.create_category(
        ctx, CreateCategoryParams(name="Pets", type=TransactionType.EXPENSE)
    )
    await registry.create_category(
        ctx, CreateCategoryParams(name="Salário", type=TransactionType.INCOME)
    )

    resultado = await registry.list_categories(
        ctx, ListCategoriesParams(type=TransactionType.INCOME)
    )

    assert isinstance(resultado, ToolSuccess)
    assert [item.name for item in resultado.data] == ["Salário"]


@pytest.mark.asyncio
async def test_criar_categoria_duplicada_devolve_business_rule_violation() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()

    primeira = await registry.create_category(
        ctx, CreateCategoryParams(name="Pets", type=TransactionType.EXPENSE)
    )
    assert isinstance(primeira, ToolSuccess)

    duplicada = await registry.create_category(
        ctx, CreateCategoryParams(name="Pets", type=TransactionType.EXPENSE)
    )

    assert isinstance(duplicada, ToolError)
    assert duplicada.code == ErrorCode.BUSINESS_RULE_VIOLATION


@pytest.mark.asyncio
async def test_criar_categoria_mesmo_nome_tipo_diferente_e_permitido() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()

    await registry.create_category(
        ctx, CreateCategoryParams(name="Casa", type=TransactionType.EXPENSE)
    )
    segunda = await registry.create_category(
        ctx, CreateCategoryParams(name="Casa", type=TransactionType.INCOME)
    )

    assert isinstance(segunda, ToolSuccess)


@pytest.mark.asyncio
async def test_get_user_preferences_devolve_preferencias_do_usuario() -> None:
    registry, _, usuarios = _novo_registry()
    ctx = _novo_contexto()
    await usuarios.add(
        User(
            id=ctx.user_id,
            name="Alexandre",
            timezone="America/Sao_Paulo",
            currency="BRL",
            locale="pt_BR",
        )
    )

    resultado = await registry.get_user_preferences(ctx, GetUserPreferencesParams())

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.timezone == "America/Sao_Paulo"
    assert resultado.data.currency == "BRL"
    assert resultado.data.locale == "pt_BR"


@pytest.mark.asyncio
async def test_get_user_preferences_usuario_inexistente_devolve_not_found() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.get_user_preferences(ctx, GetUserPreferencesParams())

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_update_user_preferences_persiste_e_e_lida_de_volta() -> None:
    registry, _, usuarios = _novo_registry()
    ctx = _novo_contexto()
    await usuarios.add(
        User(
            id=ctx.user_id,
            name="Alexandre",
            timezone="America/Sao_Paulo",
            currency="BRL",
            locale="pt_BR",
        )
    )

    atualizado = await registry.update_user_preferences(
        ctx, UpdateUserPreferencesParams(timezone="Europe/Lisbon", currency="EUR")
    )
    assert isinstance(atualizado, ToolSuccess)
    assert atualizado.data.timezone == "Europe/Lisbon"
    assert atualizado.data.currency == "EUR"

    lido = await registry.get_user_preferences(ctx, GetUserPreferencesParams())
    assert isinstance(lido, ToolSuccess)
    assert lido.data.timezone == "Europe/Lisbon"
    assert lido.data.currency == "EUR"
