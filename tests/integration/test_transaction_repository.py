import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.db import get_session_maker
from app.domain.enums import TransactionSource, TransactionType
from app.domain.user_service import UserService
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories.sqlalchemy import SqlAlchemyTransactionRepository

pytestmark = pytest.mark.integration


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


def _nova_transacao(user_id: uuid.UUID) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=user_id,
        type=TransactionType.EXPENSE,
        amount=Decimal("50.00"),
        currency="BRL",
        date=date(2026, 8, 21),
        source=TransactionSource.CHAT,
    )


@pytest.mark.asyncio
async def test_listar_transacoes_do_usuario_a_nunca_retorna_as_do_usuario_b() -> None:
    user_a = await _criar_usuario("Usuária A")
    user_b = await _criar_usuario("Usuário B")
    repo = SqlAlchemyTransactionRepository()
    try:
        transacao_a = await repo.add(user_a, _nova_transacao(user_a))
        await repo.add(user_b, _nova_transacao(user_b))

        transacoes_de_a = await repo.list_by_user(user_a)

        assert [transacao.id for transacao in transacoes_de_a] == [transacao_a.id]
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)


@pytest.mark.asyncio
async def test_buscar_por_id_transacao_de_outro_usuario_retorna_vazio() -> None:
    user_a = await _criar_usuario("Usuária A")
    user_b = await _criar_usuario("Usuário B")
    repo = SqlAlchemyTransactionRepository()
    try:
        transacao_a = await repo.add(user_a, _nova_transacao(user_a))

        assert await repo.get(user_b, transacao_a.id) is None
        assert await repo.get(user_a, transacao_a.id) is not None
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)


@pytest.mark.asyncio
async def test_atualizar_transacao_de_outro_usuario_nao_altera_nada() -> None:
    user_a = await _criar_usuario("Usuária A")
    user_b = await _criar_usuario("Usuário B")
    repo = SqlAlchemyTransactionRepository()
    try:
        transacao_a = await repo.add(user_a, _nova_transacao(user_a))

        resultado = await repo.update(user_b, transacao_a.id, amount=Decimal("999.99"))

        assert resultado is None
        intacta = await repo.get(user_a, transacao_a.id)
        assert intacta is not None
        assert intacta.amount == Decimal("50.00")
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)


@pytest.mark.asyncio
async def test_excluir_transacao_de_outro_usuario_nao_exclui_nada() -> None:
    user_a = await _criar_usuario("Usuária A")
    user_b = await _criar_usuario("Usuário B")
    repo = SqlAlchemyTransactionRepository()
    try:
        transacao_a = await repo.add(user_a, _nova_transacao(user_a))

        resultado = await repo.delete(user_b, transacao_a.id)

        assert resultado is False
        ainda_existe = await repo.get(user_a, transacao_a.id)
        assert ainda_existe is not None
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)
