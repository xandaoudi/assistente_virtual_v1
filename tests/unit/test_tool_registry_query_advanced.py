import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import TransactionType
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
    ComparePeriodsParams,
    CreateTransactionParams,
    GetMonthlyTrendParams,
    GetTopExpensesParams,
    ListTransactionsParams,
    ListTransactionsResult,
)

pytestmark = pytest.mark.unit

_INICIO = date(2026, 7, 1)
_FIM = date(2026, 7, 31)


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )


def _novo_contexto(**overrides: object) -> ToolContext:
    padrao: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "timezone": "America/Sao_Paulo",
        "currency": "BRL",
        "today": _FIM,
    }
    padrao.update(overrides)
    return ToolContext(**padrao)  # type: ignore[arg-type]


async def _criar(registry: ToolRegistry, ctx: ToolContext, **campos: object) -> None:
    padrao: dict[str, object] = {
        "type": TransactionType.EXPENSE,
        "amount": "10,00",
        "description": "Compra",
        "date": date(2026, 7, 10),
    }
    padrao.update(campos)
    resultado = await registry.create_transaction(ctx, CreateTransactionParams(**padrao))  # type: ignore[arg-type]
    assert isinstance(resultado, ToolSuccess)


@pytest.mark.asyncio
async def test_list_transactions_filtros_combinados_funcionam_em_conjunto() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto()

    await _criar(registry, ctx, description="Almoço no shopping", amount="30,00")
    await _criar(registry, ctx, description="Almoço em casa", amount="90,00")
    await _criar(
        registry, ctx, description="Salário", amount="3000,00", type=TransactionType.INCOME
    )

    resultado = await registry.list_transactions(
        ctx,
        ListTransactionsParams(
            start_date=_INICIO,
            end_date=_FIM,
            type=TransactionType.EXPENSE,
            min_amount=Decimal("50.00"),
            query="almoço",
        ),
    )

    assert isinstance(resultado, ToolSuccess)
    dados: ListTransactionsResult = resultado.data
    assert len(dados.items) == 1
    assert dados.items[0].description == "Almoço em casa"
    assert dados.truncated is False


@pytest.mark.asyncio
async def test_list_transactions_limit_e_respeitado_e_sinaliza_truncamento() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto()

    for i in range(5):
        await _criar(registry, ctx, description=f"Compra {i}", date=date(2026, 7, 1 + i))

    resultado = await registry.list_transactions(
        ctx, ListTransactionsParams(start_date=_INICIO, end_date=_FIM, limit=3)
    )

    assert isinstance(resultado, ToolSuccess)
    assert len(resultado.data.items) == 3
    assert resultado.data.truncated is True


@pytest.mark.asyncio
async def test_list_transactions_sem_truncamento_quando_cabe_tudo() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto()

    await _criar(registry, ctx)

    resultado = await registry.list_transactions(
        ctx, ListTransactionsParams(start_date=_INICIO, end_date=_FIM, limit=10)
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.truncated is False


@pytest.mark.asyncio
async def test_compare_periods_com_periodo_anterior_zerado_nao_estoura() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto()

    await _criar(registry, ctx, amount="100,00", date=date(2026, 7, 10))

    resultado = await registry.compare_periods(
        ctx,
        ComparePeriodsParams(
            period_a_start=_INICIO,
            period_a_end=_FIM,
            period_b_start=date(2026, 6, 1),
            period_b_end=date(2026, 6, 30),
        ),
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.period_a_total == Decimal("100.00")
    assert resultado.data.period_b_total == Decimal("0.00")
    assert resultado.data.percent_change is None


@pytest.mark.asyncio
async def test_compare_periods_com_group_by_devolve_validation_error() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.compare_periods(
        ctx,
        ComparePeriodsParams(
            period_a_start=_INICIO,
            period_a_end=_FIM,
            period_b_start=date(2026, 6, 1),
            period_b_end=date(2026, 6, 30),
            group_by="category",
        ),
    )

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_get_top_expenses_devolve_maiores_primeiro_respeitando_limit() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto()

    await _criar(registry, ctx, amount="10,00", description="Pequena")
    await _criar(registry, ctx, amount="500,00", description="Grande")
    await _criar(registry, ctx, amount="50,00", description="Média")

    resultado = await registry.get_top_expenses(
        ctx, GetTopExpensesParams(start_date=_INICIO, end_date=_FIM, limit=2)
    )

    assert isinstance(resultado, ToolSuccess)
    assert len(resultado.data) == 2
    assert resultado.data[0].description == "Grande"
    assert resultado.data[1].description == "Média"


@pytest.mark.asyncio
async def test_get_monthly_trend_inclui_meses_vazios() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto(today=date(2026, 8, 15))

    await _criar(registry, ctx, amount="100,00", date=date(2026, 8, 5))

    resultado = await registry.get_monthly_trend(ctx, GetMonthlyTrendParams(months=3))

    assert isinstance(resultado, ToolSuccess)
    assert len(resultado.data) == 3
    meses = [(item.year, item.month) for item in resultado.data]
    assert meses == [(2026, 6), (2026, 7), (2026, 8)]
    totais = {(item.year, item.month): item.total for item in resultado.data}
    assert totais[(2026, 6)] == Decimal("0.00")
    assert totais[(2026, 7)] == Decimal("0.00")
    assert totais[(2026, 8)] == Decimal("100.00")
