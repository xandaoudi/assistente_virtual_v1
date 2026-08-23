import uuid
from datetime import date

import pytest

from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.results import ErrorCode, ToolError, ToolSuccess
from app.tools.schemas import ResolveRelativeDateParams

pytestmark = pytest.mark.unit


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
        "today": date(2026, 8, 19),
    }
    padrao.update(overrides)
    return ToolContext(**padrao)  # type: ignore[arg-type]


_HOJE = date(2026, 8, 19)  # quarta-feira, mesma referência da tabela do T1.2

_CASOS = [
    ("hoje", date(2026, 8, 19), date(2026, 8, 19)),
    ("ontem", date(2026, 8, 18), date(2026, 8, 18)),
    ("esta semana", date(2026, 8, 17), date(2026, 8, 19)),
    ("semana passada", date(2026, 8, 10), date(2026, 8, 16)),
    ("este mês", date(2026, 8, 1), date(2026, 8, 19)),
    ("mês passado", date(2026, 7, 1), date(2026, 7, 31)),
    ("últimos 30 dias", date(2026, 7, 21), date(2026, 8, 19)),
    ("este ano", date(2026, 1, 1), date(2026, 8, 19)),
    ("em julho", date(2026, 7, 1), date(2026, 7, 31)),
]


@pytest.mark.parametrize(("expr", "inicio_esperado", "fim_esperado"), _CASOS)
@pytest.mark.asyncio
async def test_expressoes_conhecidas_devolvem_o_periodo_correto(
    expr: str, inicio_esperado: date, fim_esperado: date
) -> None:
    registry = _novo_registry()
    ctx = _novo_contexto(today=_HOJE)

    resultado = await registry.resolve_relative_date(
        ctx, ResolveRelativeDateParams(expression=expr)
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.start_date == inicio_esperado
    assert resultado.data.end_date == fim_esperado


@pytest.mark.asyncio
async def test_usa_ctx_today_nao_a_data_real_do_sistema() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto(today=date(2020, 1, 15))

    resultado = await registry.resolve_relative_date(
        ctx, ResolveRelativeDateParams(expression="hoje")
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.start_date == date(2020, 1, 15)
    assert resultado.data.end_date == date(2020, 1, 15)


@pytest.mark.asyncio
async def test_reference_date_explicito_tem_prioridade_sobre_ctx_today() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto(today=date(2026, 8, 19))

    resultado = await registry.resolve_relative_date(
        ctx, ResolveRelativeDateParams(expression="hoje", reference_date=date(2025, 1, 1))
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.start_date == date(2025, 1, 1)


@pytest.mark.asyncio
async def test_expressao_desconhecida_devolve_validation_error_com_sugestao() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.resolve_relative_date(
        ctx, ResolveRelativeDateParams(expression="depois de amanhã")
    )

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.VALIDATION_ERROR
    assert "depois de amanhã" in resultado.message
    assert "mês passado" in resultado.message


@pytest.mark.asyncio
async def test_criterio_de_aceite_mes_passado_a_partir_de_31_03_2026() -> None:
    registry = _novo_registry()
    ctx = _novo_contexto(today=date(2026, 3, 31))

    resultado = await registry.resolve_relative_date(
        ctx, ResolveRelativeDateParams(expression="mês passado")
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.start_date == date(2026, 2, 1)
    assert resultado.data.end_date == date(2026, 2, 28)
