import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.db import get_session_maker
from app.domain.enums import TransactionType
from app.domain.user_service import UserService
from app.models.tool_audit_log import ToolAuditLog
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
from app.tools.schemas import CreateTransactionParams

pytestmark = pytest.mark.integration


async def _criar_usuario() -> uuid.UUID:
    async with get_session_maker()() as session:
        user = UserService().create_user("Teste ToolRegistry Auditoria")
        session.add(user)
        await session.commit()
        return user.id


async def _remover_usuario(user_id: uuid.UUID) -> None:
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)  # ON DELETE CASCADE remove a auditoria junto
            await session.commit()


async def _todos_os_registros_de_auditoria() -> list[ToolAuditLog]:
    async with get_session_maker()() as session:
        resultado = await session.execute(select(ToolAuditLog))
        return list(resultado.scalars().all())


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        SqlAlchemyTransactionRepository(),
        SqlAlchemyCategoryRepository(),
        SqlAlchemyUserRepository(),
        SqlAlchemyToolAuditLogRepository(),
    )


@pytest.mark.asyncio
async def test_registro_persiste_e_e_consultavel_por_usuario_e_periodo() -> None:
    user_id = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx = ToolContext(
            user_id=user_id,
            timezone="America/Sao_Paulo",
            currency="BRL",
            today=datetime.now(UTC).date(),
        )

        resultado = await registry.create_transaction(
            ctx,
            CreateTransactionParams(
                type=TransactionType.EXPENSE, amount="10,00", description="Café"
            ),
        )
        assert isinstance(resultado, ToolSuccess)

        audit_repo = SqlAlchemyToolAuditLogRepository()
        agora = datetime.now(UTC)
        registros = await audit_repo.list_by_user(
            user_id, agora - timedelta(minutes=1), agora + timedelta(minutes=1)
        )

        assert len(registros) == 1
        assert registros[0].tool_name == "create_transaction"
        assert registros[0].result_status == "success"

        fora_do_periodo = await audit_repo.list_by_user(
            user_id, agora - timedelta(days=2), agora - timedelta(days=1)
        )
        assert fora_do_periodo == []
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_criterio_de_aceite_valor_e_descricao_nunca_aparecem_na_tabela_inteira() -> None:
    user_id = await _criar_usuario()
    try:
        registry = _novo_registry()
        ctx = ToolContext(
            user_id=user_id,
            timezone="America/Sao_Paulo",
            currency="BRL",
            today=datetime.now(UTC).date(),
        )

        resultado = await registry.create_transaction(
            ctx,
            CreateTransactionParams(
                type=TransactionType.EXPENSE,
                amount="1.234,56",
                description="almoço com cliente",
            ),
        )
        assert isinstance(resultado, ToolSuccess)

        todos = await _todos_os_registros_de_auditoria()
        assert len(todos) >= 1
        for registro in todos:
            bruto = str(registro.params)
            assert "1.234,56" not in bruto
            assert "almoço com cliente" not in bruto
    finally:
        await _remover_usuario(user_id)
