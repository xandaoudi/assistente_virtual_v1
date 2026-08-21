import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.db import get_session_maker
from app.domain.enums import TransactionSource, TransactionType
from app.domain.finance_service import FinanceService
from app.domain.user_service import UserService
from app.models.user import User
from app.repositories.sqlalchemy import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyTransactionRepository,
)

pytestmark = pytest.mark.integration

_HOJE = date(2026, 8, 21)


async def _criar_usuario(nome: str) -> uuid.UUID:
    async with get_session_maker()() as session:
        user = UserService().create_user(nome)
        session.add(user)
        await session.commit()
        return user.id


async def _remover_usuario(user_id: uuid.UUID) -> None:
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)  # ON DELETE CASCADE remove as transações junto
            await session.commit()


def _novo_service() -> FinanceService:
    return FinanceService(SqlAlchemyTransactionRepository(), SqlAlchemyCategoryRepository())


@pytest.mark.asyncio
async def test_ciclo_completo_criar_editar_excluir_no_postgres() -> None:
    user_id = await _criar_usuario("Ciclo completo")
    service = _novo_service()
    try:
        criada = await service.create_transaction(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("50.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_HOJE,
            description="Mercado",
        )
        transacao_id = criada.transaction.id

        editada = await service.update_transaction(
            user_id, transacao_id, amount=Decimal("65.50"), description="Mercado do mês"
        )
        assert editada is not None
        assert editada.amount == Decimal("65.50")
        assert editada.description == "Mercado do mês"

        excluida = await service.delete_transaction(user_id, transacao_id)
        assert excluida is True

        repo = SqlAlchemyTransactionRepository()
        assert await repo.get(user_id, transacao_id) is None
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_transacao_excluida_nao_entra_em_nenhum_relatorio() -> None:
    user_id = await _criar_usuario("Sem vazamento pós-exclusão")
    service = _novo_service()
    repo = SqlAlchemyTransactionRepository()
    try:
        criada = await service.create_transaction(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("40.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_HOJE,
        )
        await service.delete_transaction(user_id, criada.transaction.id)

        # Sem serviço de relatório ainda (T1.9/T1.10) — a garantia que importa aqui é que
        # a listagem que os relatórios usarão como base já exclui a transação excluída.
        transacoes_do_usuario = await repo.list_by_user(user_id)

        assert transacoes_do_usuario == []
    finally:
        await _remover_usuario(user_id)
