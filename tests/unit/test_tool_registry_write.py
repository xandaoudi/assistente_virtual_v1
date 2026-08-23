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
    CreateTransactionParams,
    CreateTransactionResult,
    DeleteTransactionParams,
    UpdateTransactionParams,
    UpdateTransactionResult,
)

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 21)


def _novo_registry() -> tuple[
    ToolRegistry, InMemoryTransactionRepository, InMemoryCategoryRepository
]:
    transacoes = InMemoryTransactionRepository()
    categorias = InMemoryCategoryRepository()
    registry = ToolRegistry(
        transacoes, categorias, InMemoryUserRepository(), InMemoryToolAuditLogRepository()
    )
    return registry, transacoes, categorias


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
async def test_criar_despesa_devolve_sucesso_com_dados_normalizados() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="45,90",
            description="Almoço",
            date=date(2026, 8, 20),
        ),
    )

    assert isinstance(resultado, ToolSuccess)
    dados: CreateTransactionResult = resultado.data
    assert dados.type == TransactionType.EXPENSE
    assert dados.amount == Decimal("45.90")
    assert dados.description == "Almoço"
    assert dados.date == date(2026, 8, 20)


@pytest.mark.asyncio
async def test_criar_sem_data_usa_ctx_today() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto(today=date(2026, 8, 19))

    resultado = await registry.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="10", description="Café"),
    )

    assert isinstance(resultado, ToolSuccess)
    assert resultado.data.date == date(2026, 8, 19)


@pytest.mark.asyncio
async def test_criar_com_valor_ambiguo_devolve_ambiguous_input_sem_gravar() -> None:
    registry, transacoes, _ = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE, amount="1.250", description="Aluguel"
        ),
    )

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.AMBIGUOUS_INPUT
    assert await transacoes.list_by_user(ctx.user_id) == []


@pytest.mark.asyncio
async def test_criar_com_valor_zero_devolve_business_rule_violation() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()

    resultado = await registry.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="0", description="Nada"),
    )

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.BUSINESS_RULE_VIOLATION


@pytest.mark.asyncio
async def test_atualizar_transacao_de_outro_usuario_devolve_not_found() -> None:
    registry, _, _ = _novo_registry()
    dono = _novo_contexto()
    invasor = _novo_contexto()

    criada = await registry.create_transaction(
        dono,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="10", description="Café"),
    )
    assert isinstance(criada, ToolSuccess)

    resultado = await registry.update_transaction(
        invasor,
        UpdateTransactionParams(transaction_id=criada.data.transaction_id, description="hackeado"),
    )

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_excluir_transacao_de_outro_usuario_devolve_not_found() -> None:
    registry, _, _ = _novo_registry()
    dono = _novo_contexto()
    invasor = _novo_contexto()

    criada = await registry.create_transaction(
        dono,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="10", description="Café"),
    )
    assert isinstance(criada, ToolSuccess)

    resultado = await registry.delete_transaction(
        invasor, DeleteTransactionParams(transaction_id=criada.data.transaction_id)
    )

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_atualizar_com_categoria_inexistente_devolve_business_rule_violation() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()

    criada = await registry.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="10", description="Café"),
    )
    assert isinstance(criada, ToolSuccess)

    resultado = await registry.update_transaction(
        ctx,
        UpdateTransactionParams(
            transaction_id=criada.data.transaction_id, category="Categoria Que Não Existe"
        ),
    )

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.BUSINESS_RULE_VIOLATION


@pytest.mark.asyncio
async def test_ciclo_criar_atualizar_excluir_em_memoria() -> None:
    registry, _, _ = _novo_registry()
    ctx = _novo_contexto()

    criada = await registry.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="10", description="Café"),
    )
    assert isinstance(criada, ToolSuccess)

    atualizada = await registry.update_transaction(
        ctx,
        UpdateTransactionParams(transaction_id=criada.data.transaction_id, description="Padaria"),
    )
    assert isinstance(atualizada, ToolSuccess)
    dados: UpdateTransactionResult = atualizada.data
    assert dados.description == "Padaria"

    excluida = await registry.delete_transaction(
        ctx, DeleteTransactionParams(transaction_id=criada.data.transaction_id)
    )
    assert isinstance(excluida, ToolSuccess)
    assert excluida.data.deleted is True


@pytest.mark.asyncio
async def test_create_transaction_repete_idempotency_key_devolve_resultado_original() -> None:
    registry, transacoes, _ = _novo_registry()
    ctx = _novo_contexto(idempotency_key="msg-123")

    primeira = await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE, amount="45,90", description="Mercado"
        ),
    )
    segunda = await registry.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="999,00", description="Outra"),
    )

    assert isinstance(primeira, ToolSuccess)
    assert isinstance(segunda, ToolSuccess)
    assert segunda.data.transaction_id == primeira.data.transaction_id
    assert segunda.data.amount == Decimal("45.90")
    assert len(await transacoes.list_by_user(ctx.user_id)) == 1
