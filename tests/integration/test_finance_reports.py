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

_INICIO = date(2026, 7, 1)
_FIM = date(2026, 7, 31)


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
async def test_relatorios_batem_com_os_mesmos_calculos_no_postgres() -> None:
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
        transporte = await category_repo.add(
            user_id,
            Category(
                id=uuid.uuid4(),
                user_id=user_id,
                name="Transporte",
                type=TransactionType.EXPENSE,
                is_active=True,
                is_default=False,
            ),
        )

        for valor, dia in [
            (Decimal("300.00"), 5),
            (Decimal("300.00"), 12),
            (Decimal("247.30"), 20),
        ]:
            await transaction_repo.add(
                user_id,
                Transaction(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    type=TransactionType.EXPENSE,
                    amount=valor,
                    currency="BRL",
                    category_id=mercado.id,
                    date=date(2026, 7, dia),
                    source=TransactionSource.CHAT,
                ),
            )
        await transaction_repo.add(
            user_id,
            Transaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.EXPENSE,
                amount=Decimal("152.70"),
                currency="BRL",
                category_id=transporte.id,
                date=date(2026, 7, 8),
                source=TransactionSource.CHAT,
            ),
        )
        await transaction_repo.add(
            user_id,
            Transaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.INCOME,
                amount=Decimal("5000.00"),
                currency="BRL",
                date=date(2026, 7, 1),
                source=TransactionSource.CHAT,
            ),
        )
        # Fora do período — não deve entrar em nenhum cálculo.
        await transaction_repo.add(
            user_id,
            Transaction(
                id=uuid.uuid4(),
                user_id=user_id,
                type=TransactionType.EXPENSE,
                amount=Decimal("999.00"),
                currency="BRL",
                category_id=mercado.id,
                date=date(2026, 8, 1),
                source=TransactionSource.CHAT,
            ),
        )

        resumo = await service.get_summary(user_id, _INICIO, _FIM)
        assert resumo.total_expenses == Decimal("1000.00")
        assert resumo.total_income == Decimal("5000.00")
        assert resumo.balance == Decimal("4000.00")

        agrupado = await service.get_spending_by_category(user_id, _INICIO, _FIM)
        por_nome = {item["category"]: item for item in agrupado}
        assert por_nome["Mercado"]["total"] == Decimal("847.30")
        assert por_nome["Mercado"]["count"] == 3
        assert por_nome["Transporte"]["total"] == Decimal("152.70")
        assert por_nome["Transporte"]["count"] == 1
        assert sum(item["percent"] for item in agrupado) == pytest.approx(100.0)

        total_mercado = await service.get_category_spending(user_id, _INICIO, _FIM, mercado.id)
        assert total_mercado == Decimal("847.30")
    finally:
        await _remover_usuario(user_id)
