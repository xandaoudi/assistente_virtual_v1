import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db import get_session_maker
from app.domain.enums import TransactionSource, TransactionType
from app.domain.user_service import UserService
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories.sqlalchemy import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyToolAuditLogRepository,
    SqlAlchemyTransactionRepository,
    SqlAlchemyUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.results import ErrorCode, ToolError, ToolSuccess
from app.tools.schemas import (
    CreateTransactionParams,
    DeleteTransactionParams,
    UpdateTransactionParams,
)

pytestmark = pytest.mark.integration

_HOJE = date(2026, 8, 21)


async def _criar_usuario() -> uuid.UUID:
    async with get_session_maker()() as session:
        user = UserService().create_user("Teste ToolRegistry")
        session.add(user)
        await session.commit()
        return user.id


async def _remover_usuario(user_id: uuid.UUID) -> None:
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)  # ON DELETE CASCADE remove as transações junto
            await session.commit()


async def _buscar_transacao(transaction_id: uuid.UUID) -> Transaction | None:
    async with get_session_maker()() as session:
        return await session.get(Transaction, transaction_id)


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        SqlAlchemyTransactionRepository(),
        SqlAlchemyCategoryRepository(),
        SqlAlchemyUserRepository(),
        SqlAlchemyToolAuditLogRepository(),
    )


def _novo_contexto(user_id: uuid.UUID) -> ToolContext:
    return ToolContext(user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_HOJE)


@pytest.mark.asyncio
async def test_ciclo_criar_atualizar_excluir_persiste_corretamente() -> None:
    user_id = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx = _novo_contexto(user_id)

        criada = await registry.create_transaction(
            ctx,
            CreateTransactionParams(
                type=TransactionType.EXPENSE, amount="45,90", description="Almoço"
            ),
        )
        assert isinstance(criada, ToolSuccess)
        transaction_id = criada.data.transaction_id

        persistida = await _buscar_transacao(transaction_id)
        assert persistida is not None
        assert persistida.amount == Decimal("45.90")

        atualizada = await registry.update_transaction(
            ctx, UpdateTransactionParams(transaction_id=transaction_id, amount="50,00")
        )
        assert isinstance(atualizada, ToolSuccess)
        assert atualizada.data.amount == Decimal("50.00")

        excluida = await registry.delete_transaction(
            ctx, DeleteTransactionParams(transaction_id=transaction_id)
        )
        assert isinstance(excluida, ToolSuccess)

        apos_exclusao = await _buscar_transacao(transaction_id)
        assert apos_exclusao is not None
        assert apos_exclusao.deleted_at is not None
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_falha_no_meio_da_atualizacao_nao_deixa_gravacao_parcial() -> None:
    user_id = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx = _novo_contexto(user_id)

        criada = await registry.create_transaction(
            ctx,
            CreateTransactionParams(
                type=TransactionType.EXPENSE, amount="10,00", description="Café"
            ),
        )
        assert isinstance(criada, ToolSuccess)
        transaction_id = criada.data.transaction_id

        resultado = await registry.update_transaction(
            ctx,
            UpdateTransactionParams(
                transaction_id=transaction_id,
                description="Padaria",
                category="Categoria Que Não Existe",
            ),
        )

        assert isinstance(resultado, ToolError)
        assert resultado.code == ErrorCode.BUSINESS_RULE_VIOLATION

        inalterada = await _buscar_transacao(transaction_id)
        assert inalterada is not None
        assert inalterada.description == "Café"
        assert inalterada.amount == Decimal("10.00")
    finally:
        await _remover_usuario(user_id)


async def _transacoes_do_usuario(user_id: uuid.UUID) -> list[Transaction]:
    async with get_session_maker()() as session:
        resultado = await session.execute(select(Transaction).where(Transaction.user_id == user_id))
        return list(resultado.scalars().all())


@pytest.mark.asyncio
async def test_duas_chamadas_concorrentes_com_mesma_idempotency_key_criam_uma_transacao() -> None:
    user_id = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx = ToolContext(
            user_id=user_id,
            timezone="America/Sao_Paulo",
            currency="BRL",
            today=_HOJE,
            idempotency_key="webhook-msg-42",
        )

        resultados = await asyncio.gather(
            registry.create_transaction(
                ctx,
                CreateTransactionParams(
                    type=TransactionType.EXPENSE, amount="50,00", description="Mercado"
                ),
            ),
            registry.create_transaction(
                ctx,
                CreateTransactionParams(
                    type=TransactionType.EXPENSE, amount="50,00", description="Mercado"
                ),
            ),
        )

        assert all(isinstance(r, ToolSuccess) for r in resultados)
        ids = {r.data.transaction_id for r in resultados if isinstance(r, ToolSuccess)}
        assert len(ids) == 1

        transacoes = await _transacoes_do_usuario(user_id)
        assert len(transacoes) == 1
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_restricao_de_unicidade_de_idempotency_key_existe_no_banco() -> None:
    user_id = await _criar_usuario()
    try:
        async with get_session_maker()() as session:
            session.add(
                Transaction(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    type=TransactionType.EXPENSE,
                    amount=Decimal("10.00"),
                    currency="BRL",
                    date=_HOJE,
                    source=TransactionSource.CHAT,
                    idempotency_key="msg-duplicada",
                )
            )
            await session.commit()

        with pytest.raises(IntegrityError):
            async with get_session_maker()() as session:
                session.add(
                    Transaction(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        type=TransactionType.EXPENSE,
                        amount=Decimal("20.00"),
                        currency="BRL",
                        date=_HOJE,
                        source=TransactionSource.CHAT,
                        idempotency_key="msg-duplicada",
                    )
                )
                await session.commit()
    finally:
        await _remover_usuario(user_id)
