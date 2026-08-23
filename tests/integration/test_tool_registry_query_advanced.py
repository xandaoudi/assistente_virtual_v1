import uuid
from datetime import date

import pytest

from app.core.db import get_session_maker
from app.domain.enums import TransactionType
from app.domain.user_service import UserService
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
from app.tools.schemas import CreateTransactionParams, ListTransactionsParams

pytestmark = pytest.mark.integration

_INICIO = date(2026, 7, 1)
_FIM = date(2026, 7, 31)


async def _criar_usuario() -> uuid.UUID:
    async with get_session_maker()() as session:
        user = UserService().create_user("Teste ToolRegistry Query Avançada")
        session.add(user)
        await session.commit()
        return user.id


async def _remover_usuario(user_id: uuid.UUID) -> None:
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
            await session.commit()


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        SqlAlchemyTransactionRepository(),
        SqlAlchemyCategoryRepository(),
        SqlAlchemyUserRepository(),
        SqlAlchemyToolAuditLogRepository(),
    )


def _novo_contexto(user_id: uuid.UUID) -> ToolContext:
    return ToolContext(user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_FIM)


@pytest.mark.asyncio
async def test_listagem_grande_respeita_o_teto_e_sinaliza_truncamento() -> None:
    user_id = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx = _novo_contexto(user_id)

        for dia in range(1, 6):
            criada = await registry.create_transaction(
                ctx,
                CreateTransactionParams(
                    type=TransactionType.EXPENSE,
                    amount="10,00",
                    description=f"Compra dia {dia}",
                    date=date(2026, 7, dia),
                ),
            )
            assert isinstance(criada, ToolSuccess)

        resultado = await registry.list_transactions(
            ctx, ListTransactionsParams(start_date=_INICIO, end_date=_FIM, limit=3)
        )

        assert isinstance(resultado, ToolSuccess)
        assert len(resultado.data.items) == 3
        assert resultado.data.truncated is True
    finally:
        await _remover_usuario(user_id)
