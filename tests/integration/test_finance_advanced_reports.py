import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.db import get_session_maker
from app.domain.enums import TransactionSource, TransactionType
from app.domain.finance_service import FinanceService
from app.domain.user_service import UserService
from app.models.category import Category
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
async def test_relatorios_avancados_batem_com_os_mesmos_calculos_no_postgres() -> None:
    user_id = await _criar_usuario("Alexandre")
    category_repo = SqlAlchemyCategoryRepository()
    transaction_repo = SqlAlchemyTransactionRepository()
    service = FinanceService(transaction_repo, category_repo)
    try:
        mercado = await category_repo.add(
            user_id,
            Category(
                id=uuid.uuid4(),
                user_id=user_id,
                name="Mercado",
                type=TransactionType.EXPENSE,
                is_active=True,
                is_default=False,
            ),
        )

        # Junho: R$100. Julho: R$50 (Mercado, "Almoço") + R$300 (Mercado). Agosto: sem dados.
        await transaction_repo.add(
            user_id,
            Transaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.EXPENSE,
                amount=Decimal("100.00"),
                currency="BRL",
                category_id=mercado.id,
                date=date(2026, 6, 15),
                source=TransactionSource.CHAT,
            ),
        )
        await transaction_repo.add(
            user_id,
            Transaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.EXPENSE,
                amount=Decimal("50.00"),
                currency="BRL",
                category_id=mercado.id,
                date=date(2026, 7, 10),
                description="Almoço no trabalho",
                source=TransactionSource.CHAT,
            ),
        )
        await transaction_repo.add(
            user_id,
            Transaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.EXPENSE,
                amount=Decimal("300.00"),
                currency="BRL",
                category_id=mercado.id,
                date=date(2026, 7, 20),
                source=TransactionSource.CHAT,
            ),
        )

        comparacao = await service.compare_periods(
            user_id,
            current_start=date(2026, 7, 1),
            current_end=date(2026, 7, 31),
            previous_start=date(2026, 6, 1),
            previous_end=date(2026, 6, 30),
        )
        assert comparacao.current_total == Decimal("350.00")
        assert comparacao.previous_total == Decimal("100.00")
        assert comparacao.absolute_change == Decimal("250.00")
        assert comparacao.percent_change == 250.0

        listagem = await service.list_transactions(
            user_id, date(2026, 7, 1), date(2026, 7, 31), text="almoco"
        )
        assert len(listagem) == 1
        assert listagem[0].amount == Decimal("50.00")

        top = await service.get_top_expenses(user_id, date(2026, 7, 1), date(2026, 7, 31), 1)
        assert len(top) == 1
        assert top[0].amount == Decimal("300.00")

        serie = await service.get_monthly_trend(user_id, date(2026, 6, 1), date(2026, 8, 31))
        assert [(item.year, item.month, item.total) for item in serie] == [
            (2026, 6, Decimal("100.00")),
            (2026, 7, Decimal("350.00")),
            (2026, 8, Decimal("0.00")),
        ]
    finally:
        await _remover_usuario(user_id)
