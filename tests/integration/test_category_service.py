import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.db import get_session_maker
from app.domain.category_service import CategoryService
from app.domain.enums import TransactionSource, TransactionType
from app.domain.user_service import UserService
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories.sqlalchemy import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyTransactionRepository,
)

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
            await session.delete(user)  # ON DELETE CASCADE remove categorias/transações junto
            await session.commit()


@pytest.mark.asyncio
async def test_desativar_categoria_com_transacoes_preserva_transacoes_e_vinculo() -> None:
    user_id = await _criar_usuario("Usuária")
    transaction_repo = SqlAlchemyTransactionRepository()
    service = CategoryService(SqlAlchemyCategoryRepository())
    try:
        categoria = await service.create_category(user_id, "Mercado", TransactionType.EXPENSE)
        transacao = await transaction_repo.add(
            user_id,
            Transaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.EXPENSE,
                amount=Decimal("120.00"),
                currency="BRL",
                category_id=categoria.id,
                date=date(2026, 7, 15),
                source=TransactionSource.CHAT,
            ),
        )

        desativada = await service.deactivate_category(user_id, categoria.id)
        assert desativada is not None
        assert desativada.is_active is False

        transacao_recuperada = await transaction_repo.get(user_id, transacao.id)
        assert transacao_recuperada is not None
        assert transacao_recuperada.category_id == categoria.id
        assert transacao_recuperada.amount == Decimal("120.00")
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_categoria_desativada_ainda_aparece_ao_consultar_periodo_anterior() -> None:
    user_id = await _criar_usuario("Usuária")
    category_repo = SqlAlchemyCategoryRepository()
    service = CategoryService(category_repo)
    try:
        categoria = await service.create_category(user_id, "Mercado", TransactionType.EXPENSE)
        await service.deactivate_category(user_id, categoria.id)

        # Um relatório de período anterior busca a categoria pelo `category_id` gravado na
        # transação, não pela listagem padrão (que omite as inativas) — precisa continuar
        # enxergando o nome dela.
        categoria_historica = await category_repo.get(user_id, categoria.id)
        assert categoria_historica is not None
        assert categoria_historica.name == "Mercado"
        assert categoria_historica.is_active is False
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_listagem_padrao_omite_as_desativadas() -> None:
    user_id = await _criar_usuario("Usuária")
    service = CategoryService(SqlAlchemyCategoryRepository())
    try:
        ativa = await service.create_category(user_id, "Mercado", TransactionType.EXPENSE)
        inativa = await service.create_category(user_id, "Lazer", TransactionType.EXPENSE)
        await service.deactivate_category(user_id, inativa.id)

        listagem = await service.list_categories(user_id)

        nomes = {categoria.name for categoria in listagem}
        assert ativa.name in nomes
        assert inativa.name not in nomes
    finally:
        await _remover_usuario(user_id)
