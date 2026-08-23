import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.db import get_session_maker
from app.domain.enums import TransactionType
from app.domain.finance_service import FinanceService
from app.domain.user_service import UserService
from app.models.category import Category
from app.models.user import User
from app.repositories.sqlalchemy import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyToolAuditLogRepository,
    SqlAlchemyTransactionRepository,
    SqlAlchemyUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.results import ToolSuccess
from app.tools.schemas import (
    CreateTransactionParams,
    GetCategorySpendingParams,
    GetSpendingByCategoryParams,
    GetSummaryParams,
)

pytestmark = pytest.mark.integration

_INICIO = date(2026, 7, 1)
_FIM = date(2026, 7, 31)


async def _criar_usuario() -> uuid.UUID:
    async with get_session_maker()() as session:
        user = UserService().create_user("Teste ToolRegistry Query")
        session.add(user)
        await session.commit()
        return user.id


async def _remover_usuario(user_id: uuid.UUID) -> None:
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
            await session.commit()


async def _criar_categoria(user_id: uuid.UUID, name: str) -> Category:
    async with get_session_maker()() as session:
        categoria = Category(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            type=TransactionType.EXPENSE,
            is_active=True,
            is_default=False,
        )
        session.add(categoria)
        await session.commit()
        return categoria


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        SqlAlchemyTransactionRepository(),
        SqlAlchemyCategoryRepository(),
        SqlAlchemyUserRepository(),
        SqlAlchemyToolAuditLogRepository(),
    )


def _novo_service() -> FinanceService:
    return FinanceService(SqlAlchemyTransactionRepository(), SqlAlchemyCategoryRepository())


def _novo_contexto(user_id: uuid.UUID) -> ToolContext:
    return ToolContext(user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_FIM)


@pytest.mark.asyncio
async def test_resultados_da_tool_batem_com_o_finance_service_direto() -> None:
    user_id = await _criar_usuario()
    try:
        mercado = await _criar_categoria(user_id, "Mercado")
        registry = _novo_registry()
        ctx = _novo_contexto(user_id)

        for valor in ("300,00", "250,00", "297,30"):
            criada = await registry.create_transaction(
                ctx,
                CreateTransactionParams(
                    type=TransactionType.EXPENSE,
                    amount=valor,
                    description="Compra",
                    category=mercado.name,
                    date=date(2026, 7, 15),
                ),
            )
            assert isinstance(criada, ToolSuccess)

        service = _novo_service()
        resumo_direto = await service.get_summary(user_id, _INICIO, _FIM)
        agrupado_direto = await service.get_spending_by_category(user_id, _INICIO, _FIM)
        total_direto = await service.get_category_spending(user_id, _INICIO, _FIM, mercado.id)

        resultado_summary = await registry.get_summary(
            ctx, GetSummaryParams(start_date=_INICIO, end_date=_FIM)
        )
        resultado_agrupado = await registry.get_spending_by_category(
            ctx, GetSpendingByCategoryParams(start_date=_INICIO, end_date=_FIM)
        )
        resultado_categoria = await registry.get_category_spending(
            ctx,
            GetCategorySpendingParams(category="Mercado", start_date=_INICIO, end_date=_FIM),
        )

        assert isinstance(resultado_summary, ToolSuccess)
        assert resultado_summary.data.total_expenses == resumo_direto.total_expenses
        assert resultado_summary.data.transaction_count == resumo_direto.transaction_count

        assert isinstance(resultado_agrupado, ToolSuccess)
        assert len(resultado_agrupado.data) == len(agrupado_direto)
        assert resultado_agrupado.data[0].total == agrupado_direto[0]["total"]
        assert resultado_agrupado.data[0].category == agrupado_direto[0]["category"]

        assert isinstance(resultado_categoria, ToolSuccess)
        assert resultado_categoria.data.total == total_direto
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_consulta_nunca_retorna_dado_de_outro_usuario() -> None:
    user_a = await _criar_usuario()
    user_b = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx_a = _novo_contexto(user_a)
        ctx_b = _novo_contexto(user_b)

        await registry.create_transaction(
            ctx_a,
            CreateTransactionParams(
                type=TransactionType.EXPENSE,
                amount="1000,00",
                description="Só do usuário A",
                date=date(2026, 7, 10),
            ),
        )

        resultado_b = await registry.get_summary(
            ctx_b, GetSummaryParams(start_date=_INICIO, end_date=_FIM)
        )

        assert isinstance(resultado_b, ToolSuccess)
        assert resultado_b.data.total_expenses == Decimal("0.00")
        assert resultado_b.data.transaction_count == 0
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)
