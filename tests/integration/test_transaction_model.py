import asyncio
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect, select

from alembic import command
from app.core.db import get_engine, get_session_maker
from app.domain.enums import TransactionSource, TransactionType
from app.domain.user_service import UserService
from app.models.transaction import Transaction
from app.models.user import User

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


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


def _nova_transacao(user_id: uuid.UUID, **overrides: object) -> Transaction:
    campos: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "type": TransactionType.EXPENSE,
        "amount": Decimal("45.00"),
        "currency": "BRL",
        "date": date(2026, 8, 21),
        "source": TransactionSource.CHAT,
    }
    campos.update(overrides)
    return Transaction(**campos)


@pytest.mark.asyncio
async def test_valor_grande_faz_round_trip_exato_sem_perda_de_precisao() -> None:
    user_id = await _criar_usuario("Precisão")
    try:
        transacao_id = uuid.uuid4()
        async with get_session_maker()() as session:
            session.add(_nova_transacao(user_id, id=transacao_id, amount=Decimal("1234567.89")))
            await session.commit()

        async with get_session_maker()() as session:
            recuperada = await session.get(Transaction, transacao_id)
            assert recuperada is not None
            assert recuperada.amount == Decimal("1234567.89")
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_coluna_amount_e_numeric_nao_double_precision() -> None:
    async with get_engine().connect() as conn:
        colunas = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_columns("transactions")
        )

    coluna_amount = next(coluna for coluna in colunas if coluna["name"] == "amount")
    assert isinstance(coluna_amount["type"], sa.Numeric)
    assert not isinstance(coluna_amount["type"], sa.Float)


@pytest.mark.asyncio
async def test_soft_delete_some_da_consulta_padrao_mas_registro_permanece_na_tabela() -> None:
    user_id = await _criar_usuario("Soft delete")
    try:
        transacao_id = uuid.uuid4()
        async with get_session_maker()() as session:
            session.add(_nova_transacao(user_id, id=transacao_id))
            await session.commit()

            transacao = await session.get(Transaction, transacao_id)
            assert transacao is not None
            transacao.deleted_at = datetime.now(UTC)
            await session.commit()

        async with get_session_maker()() as session:
            consulta_padrao = (
                await session.execute(
                    select(Transaction).where(
                        Transaction.user_id == user_id, Transaction.deleted_at.is_(None)
                    )
                )
            ).scalar_one_or_none()
            assert consulta_padrao is None

            ainda_na_tabela = await session.get(Transaction, transacao_id)
            assert ainda_na_tabela is not None
            assert ainda_na_tabela.deleted_at is not None
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_indices_compostos_existem() -> None:
    async with get_engine().connect() as conn:
        indices = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_indexes("transactions")
        )

    colunas_por_indice = {tuple(indice["column_names"]) for indice in indices}
    assert ("user_id", "date") in colunas_por_indice
    assert ("user_id", "category_id", "date") in colunas_por_indice


async def _tabelas_existentes_async() -> set[str]:
    async with get_engine().connect() as conn:
        return set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))


def _tabelas_existentes() -> set[str]:
    return asyncio.run(_tabelas_existentes_async())


@pytest.mark.integration
def test_upgrade_cria_tabela_transactions_e_downgrade_remove() -> None:
    # Sem @pytest.mark.asyncio de propósito — mesmo motivo do T1.3 (asyncio.run interno).
    cfg = _alembic_config()
    try:
        command.upgrade(cfg, "head")
        assert "transactions" in _tabelas_existentes()

        command.downgrade(cfg, "-1")
        assert "transactions" not in _tabelas_existentes()
    finally:
        command.upgrade(cfg, "head")
