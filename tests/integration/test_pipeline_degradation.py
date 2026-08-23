"""T3.9 — regra de ouro da degradação: uma operação já confirmada no banco não pode se
perder por causa de uma falha na etapa seguinte (RF-71, RNF-16)."""

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent
from app.adapters.channel_message import ChannelMessage
from app.adapters.message_pipeline import process_channel_message
from app.adapters.pipeline_errors import OperationConfirmedResponseFailedError, safe_message_for
from app.adapters.tools import register_tools
from app.core.db import get_session_maker
from app.domain.conversation_service import ConversationService
from app.domain.user_service import UserService
from app.models.user import User
from app.repositories.memory import InMemoryConversationRepository
from app.repositories.sqlalchemy import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyToolAuditLogRepository,
    SqlAlchemyTransactionRepository,
    SqlAlchemyUserRepository,
)
from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.integration

_HOJE = date(2026, 8, 23)


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
            await session.delete(user)  # ON DELETE CASCADE remove a transação junto
            await session.commit()


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        SqlAlchemyTransactionRepository(),
        SqlAlchemyCategoryRepository(),
        SqlAlchemyUserRepository(),
        SqlAlchemyToolAuditLogRepository(),
    )


def _mensagem() -> ChannelMessage:
    return ChannelMessage(
        channel="telegram",
        external_user_id="999",
        text="gastei 45 no mercado",
        media=None,
        timestamp=datetime.fromtimestamp(1735000000, tz=UTC),
        message_id="700",
    )


@pytest.mark.asyncio
async def test_transacao_gravada_mais_falha_na_resposta_informa_usuario_do_sucesso() -> None:
    user_id = await _criar_usuario("Usuária com falha na resposta")
    try:
        registry = _novo_registry()

        def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name="create_transaction",
                            args={
                                "params": {
                                    "type": "expense",
                                    "amount": "45,00",
                                    "description": "Mercado",
                                    "date": str(_HOJE),
                                }
                            },
                        )
                    ]
                )
            # A transação já foi commitada no Postgres neste ponto — é a etapa seguinte,
            # a redação da resposta, que falha.
            raise ModelHTTPError(status_code=503, model_name="gemini-teste")

        agent = create_agent(model=FunctionModel(roteiro))
        register_tools(agent)

        async def resolve_deps(message: ChannelMessage) -> Deps:
            return Deps(
                user_id=user_id,
                timezone="America/Sao_Paulo",
                currency="BRL",
                today=_HOJE,
                tools=registry,
            )

        resposta = await process_channel_message(
            _mensagem(),
            agent=agent,
            conversation_service=ConversationService(InMemoryConversationRepository()),
            resolve_deps=resolve_deps,
            max_history_messages=20,
        )

        assert resposta == safe_message_for(OperationConfirmedResponseFailedError())

        transacoes = await SqlAlchemyTransactionRepository().list_by_user(user_id)
        assert len(transacoes) == 1
        assert str(transacoes[0].amount) == "45.00"
    finally:
        await _remover_usuario(user_id)
