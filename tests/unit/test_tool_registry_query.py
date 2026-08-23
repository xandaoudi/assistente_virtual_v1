import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import TransactionType
from app.models.category import Category
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
    CategorySpendingItem,
    CreateTransactionParams,
    GetCategorySpendingParams,
    GetCategorySpendingResult,
    GetSpendingByCategoryParams,
    GetSummaryParams,
    GetSummaryResult,
)

pytestmark = pytest.mark.unit

_INICIO = date(2026, 7, 1)
_FIM = date(2026, 7, 31)


def _novo_registry() -> tuple[ToolRegistry, InMemoryCategoryRepository]:
    categorias = InMemoryCategoryRepository()
    registry = ToolRegistry(
        InMemoryTransactionRepository(),
        categorias,
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )
    return registry, categorias


def _novo_contexto(**overrides: object) -> ToolContext:
    padrao: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "timezone": "America/Sao_Paulo",
        "currency": "BRL",
        "today": _FIM,
    }
    padrao.update(overrides)
    return ToolContext(**padrao)  # type: ignore[arg-type]


def _nova_categoria(user_id: uuid.UUID, name: str) -> Category:
    return Category(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        type=TransactionType.EXPENSE,
        is_active=True,
        is_default=False,
    )


@pytest.mark.asyncio
async def test_get_summary_devolve_formato_do_schema_de_saida() -> None:
    registry, _ = _novo_registry()
    ctx = _novo_contexto()

    await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="50,00",
            description="Mercado",
            date=date(2026, 7, 10),
        ),
    )

    resultado = await registry.get_summary(ctx, GetSummaryParams(start_date=_INICIO, end_date=_FIM))

    assert isinstance(resultado, ToolSuccess)
    dados: GetSummaryResult = resultado.data
    assert dados.total_expenses == Decimal("50.00")
    assert dados.transaction_count == 1


@pytest.mark.asyncio
async def test_get_summary_periodo_vazio_devolve_zeros_com_sucesso() -> None:
    registry, _ = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.get_summary(ctx, GetSummaryParams(start_date=_INICIO, end_date=_FIM))

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.total_expenses == Decimal("0.00")
    assert resultado.data.total_income == Decimal("0.00")
    assert resultado.data.balance == Decimal("0.00")
    assert resultado.data.transaction_count == 0


@pytest.mark.asyncio
async def test_get_summary_valores_chegam_como_decimal_exato() -> None:
    registry, _ = _novo_registry()
    ctx = _novo_contexto()

    await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="1.234.567,89",
            description="Imóvel",
            date=date(2026, 7, 10),
        ),
    )

    resultado = await registry.get_summary(ctx, GetSummaryParams(start_date=_INICIO, end_date=_FIM))

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.total_expenses == Decimal("1234567.89")


@pytest.mark.asyncio
async def test_get_spending_by_category_devolve_formato_do_schema_de_saida() -> None:
    registry, _ = _novo_registry()
    ctx = _novo_contexto()

    criada = await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="847,30",
            description="Compras do mês",
            date=date(2026, 7, 10),
        ),
    )
    assert isinstance(criada, ToolSuccess)

    resultado = await registry.get_spending_by_category(
        ctx, GetSpendingByCategoryParams(start_date=_INICIO, end_date=_FIM)
    )

    assert isinstance(resultado, ToolSuccess)
    itens: list[CategorySpendingItem] = resultado.data
    assert len(itens) == 1
    assert itens[0].category == "Outros"
    assert itens[0].total == Decimal("847.30")
    assert itens[0].percent == 100.0
    assert itens[0].count == 1


@pytest.mark.asyncio
async def test_get_spending_by_category_periodo_vazio_devolve_lista_vazia_com_sucesso() -> None:
    registry, _ = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.get_spending_by_category(
        ctx, GetSpendingByCategoryParams(start_date=_INICIO, end_date=_FIM)
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data == []


@pytest.mark.asyncio
async def test_get_category_spending_devolve_formato_do_schema_de_saida() -> None:
    registry, categorias = _novo_registry()
    ctx = _novo_contexto()
    mercado = await categorias.add(ctx.user_id, _nova_categoria(ctx.user_id, "Mercado"))

    await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="40,00",
            description="Feira",
            category=mercado.name,
            date=date(2026, 7, 5),
        ),
    )
    await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="20,00",
            description="Padaria",
            category=mercado.name,
            date=date(2026, 7, 6),
        ),
    )

    resultado = await registry.get_category_spending(
        ctx, GetCategorySpendingParams(category="Mercado", start_date=_INICIO, end_date=_FIM)
    )

    assert isinstance(resultado, ToolSuccess)
    dados: GetCategorySpendingResult = resultado.data
    assert dados.total == Decimal("60.00")
    assert dados.count == 2
    assert dados.average == Decimal("30.00")


@pytest.mark.asyncio
async def test_get_category_spending_periodo_vazio_devolve_zeros_com_sucesso() -> None:
    registry, categorias = _novo_registry()
    ctx = _novo_contexto()
    await categorias.add(ctx.user_id, _nova_categoria(ctx.user_id, "Mercado"))

    resultado = await registry.get_category_spending(
        ctx, GetCategorySpendingParams(category="Mercado", start_date=_INICIO, end_date=_FIM)
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.total == Decimal("0.00")
    assert resultado.data.count == 0
    assert resultado.data.average == Decimal("0.00")


@pytest.mark.asyncio
async def test_get_category_spending_categoria_inexistente_devolve_business_rule_violation() -> (
    None
):
    registry, _ = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.get_category_spending(
        ctx,
        GetCategorySpendingParams(category="Categoria Fantasma", start_date=_INICIO, end_date=_FIM),
    )

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.BUSINESS_RULE_VIOLATION
