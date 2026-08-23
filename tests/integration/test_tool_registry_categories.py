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
from app.tools.schemas import (
    CreateCategoryParams,
    GetUserPreferencesParams,
    ListCategoriesParams,
    UpdateUserPreferencesParams,
)

pytestmark = pytest.mark.integration


async def _criar_usuario() -> uuid.UUID:
    async with get_session_maker()() as session:
        user = UserService().create_user("Teste ToolRegistry Categorias")
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
    return ToolContext(
        user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=date(2026, 8, 21)
    )


@pytest.mark.asyncio
async def test_preferencia_alterada_persiste_e_e_lida_de_volta() -> None:
    user_id = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx = _novo_contexto(user_id)

        atualizado = await registry.update_user_preferences(
            ctx, UpdateUserPreferencesParams(timezone="Europe/Lisbon", currency="EUR")
        )
        assert isinstance(atualizado, ToolSuccess)

        # Novo registry/sessão — prova que persistiu no banco, não só num objeto em memória.
        outro_registry = _novo_registry()
        lido = await outro_registry.get_user_preferences(ctx, GetUserPreferencesParams())

        assert isinstance(lido, ToolSuccess)
        assert lido.data.timezone == "Europe/Lisbon"
        assert lido.data.currency == "EUR"
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_categorias_de_outro_usuario_nao_aparecem() -> None:
    user_a = await _criar_usuario()
    user_b = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx_a = _novo_contexto(user_a)
        ctx_b = _novo_contexto(user_b)

        criada = await registry.create_category(
            ctx_a, CreateCategoryParams(name="Só de A", type=TransactionType.EXPENSE)
        )
        assert isinstance(criada, ToolSuccess)

        resultado_b = await registry.list_categories(ctx_b, ListCategoriesParams())

        assert isinstance(resultado_b, ToolSuccess)
        assert resultado_b.data == []
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)
