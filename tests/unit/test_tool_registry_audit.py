import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.enums import TransactionType
from app.models.tool_audit_log import ToolAuditLog
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.results import ToolError, ToolSuccess
from app.tools.schemas import CreateTransactionParams

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 21)


class _AuditRepositorioQueFalha:
    async def add(self, entry: ToolAuditLog) -> ToolAuditLog:
        raise RuntimeError("banco de auditoria fora do ar")

    async def list_by_user(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[ToolAuditLog]:
        return []


def _novo_registry(
    audit_repo: InMemoryToolAuditLogRepository | None = None,
) -> tuple[ToolRegistry, InMemoryToolAuditLogRepository]:
    auditoria = audit_repo or InMemoryToolAuditLogRepository()
    registry = ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        auditoria,
    )
    return registry, auditoria


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
async def test_chamada_bem_sucedida_gera_registro_com_status_de_sucesso() -> None:
    registry, auditoria = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="10,00", description="Café"),
    )
    assert isinstance(resultado, ToolSuccess)

    registros = await auditoria.list_by_user(
        ctx.user_id,
        datetime.now(UTC) - timedelta(minutes=1),
        datetime.now(UTC) + timedelta(minutes=1),
    )
    assert len(registros) == 1
    assert registros[0].tool_name == "create_transaction"
    assert registros[0].result_status == "success"
    assert registros[0].duration_ms >= 0


@pytest.mark.asyncio
async def test_chamada_com_erro_gera_registro_com_o_codigo_do_erro() -> None:
    registry, auditoria = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="0", description="Nada"),
    )
    assert isinstance(resultado, ToolError)

    registros = await auditoria.list_by_user(
        ctx.user_id,
        datetime.now(UTC) - timedelta(minutes=1),
        datetime.now(UTC) + timedelta(minutes=1),
    )
    assert len(registros) == 1
    assert registros[0].result_status == resultado.code.value


@pytest.mark.asyncio
async def test_amount_nao_aparece_em_texto_claro_no_registro() -> None:
    registry, auditoria = _novo_registry()
    ctx = _novo_contexto()

    await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE, amount="1.234,56", description="almoço com cliente"
        ),
    )

    registros = await auditoria.list_by_user(
        ctx.user_id,
        datetime.now(UTC) - timedelta(minutes=1),
        datetime.now(UTC) + timedelta(minutes=1),
    )
    assert len(registros) == 1
    assert "1.234,56" not in str(registros[0].params)


@pytest.mark.asyncio
async def test_description_nao_aparece_em_texto_claro_no_registro() -> None:
    registry, auditoria = _novo_registry()
    ctx = _novo_contexto()

    await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE, amount="1.234,56", description="almoço com cliente"
        ),
    )

    registros = await auditoria.list_by_user(
        ctx.user_id,
        datetime.now(UTC) - timedelta(minutes=1),
        datetime.now(UTC) + timedelta(minutes=1),
    )
    assert len(registros) == 1
    assert "almoço com cliente" not in str(registros[0].params)


@pytest.mark.asyncio
async def test_campos_nao_sensiveis_aparecem_no_registro() -> None:
    registry, auditoria = _novo_registry()
    ctx = _novo_contexto()

    await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="10,00",
            description="Café",
            date=date(2026, 8, 20),
            category="Alimentação",
        ),
    )

    registros = await auditoria.list_by_user(
        ctx.user_id,
        datetime.now(UTC) - timedelta(minutes=1),
        datetime.now(UTC) + timedelta(minutes=1),
    )
    assert registros[0].params["type"] == "expense"
    assert registros[0].params["date"] == "2026-08-20"
    assert registros[0].params["category"] == "Alimentação"


@pytest.mark.asyncio
async def test_falha_ao_gravar_auditoria_nao_derruba_a_operacao_principal() -> None:
    registry_com_falha = ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        _AuditRepositorioQueFalha(),
    )
    ctx = _novo_contexto()

    resultado = await registry_com_falha.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="10,00", description="Café"),
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.amount == 10
