"""T3.7 — idempotência de ponta a ponta (T2.11): a mesma mensagem processada mais de uma
vez nunca gera uma segunda transação, seja repetida pelo mesmo canal ou entre canais."""

import asyncio
import uuid
from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent
from app.adapters.channel_message import ChannelMessage
from app.adapters.message_pipeline import ResolveDeps, idempotency_key_for, process_channel_message
from app.adapters.tools import register_tools
from app.api.telegram_webhook import build_telegram_webhook_router
from app.core.db import get_session_maker
from app.domain.conversation_service import ConversationService
from app.domain.usage_service import UsageService
from app.domain.user_service import UserService
from app.models.user import User
from app.repositories.memory import InMemoryConversationRepository
from app.repositories.sqlalchemy import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyToolAuditLogRepository,
    SqlAlchemyTransactionRepository,
    SqlAlchemyUsageLogRepository,
    SqlAlchemyUserRepository,
)
from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.integration

_HOJE = date(2026, 8, 23)
_SECRET = "segredo-integration"
_HEADER = "X-Telegram-Bot-Api-Secret-Token"


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


def _mensagem(user_chat_id: str, message_id: str) -> ChannelMessage:
    return ChannelMessage(
        channel="telegram",
        external_user_id=user_chat_id,
        text="gastei 45 no mercado ontem",
        media=None,
        timestamp=datetime.fromtimestamp(1735000000, tz=UTC),
        message_id=message_id,
    )


def _roteiro_cria_transacao(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
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
    return ModelResponse(parts=[TextPart(content="Registrado.")])


async def _total_de_transacoes(user_id: uuid.UUID) -> int:
    return len(await SqlAlchemyTransactionRepository().list_by_user(user_id))


def _novo_usage_service() -> UsageService:
    return UsageService(SqlAlchemyUsageLogRepository())


def _resolve_deps_para(user_id: uuid.UUID) -> ResolveDeps:
    async def resolve_deps(message: ChannelMessage) -> Deps:
        return Deps(
            user_id=user_id,
            timezone="America/Sao_Paulo",
            currency="BRL",
            today=_HOJE,
            tools=_novo_registry(),
            idempotency_key=idempotency_key_for(message),
        )

    return resolve_deps


@pytest.mark.asyncio
async def test_mesma_mensagem_entregue_duas_vezes_gera_uma_transacao() -> None:
    user_id = await _criar_usuario("Usuária A")
    try:
        agent = create_agent(model=FunctionModel(_roteiro_cria_transacao))
        register_tools(agent)
        mensagem = _mensagem("999", "500")

        for _ in range(2):
            # Histórico novo a cada chamada: simula duas entregas independentes da mesma
            # mensagem (é exatamente isso que o Telegram faz num retry), sem depender de
            # continuidade de conversa para a idempotência valer.
            await process_channel_message(
                mensagem,
                agent=agent,
                conversation_service=ConversationService(InMemoryConversationRepository()),
                resolve_deps=_resolve_deps_para(user_id),
                usage_service=_novo_usage_service(),
                max_history_messages=20,
            )

        assert await _total_de_transacoes(user_id) == 1
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_mesma_mensagem_por_polling_e_depois_por_webhook_gera_uma_transacao() -> None:
    user_id = await _criar_usuario("Usuária B")
    try:
        agent = create_agent(model=FunctionModel(_roteiro_cria_transacao))
        register_tools(agent)
        mensagem = _mensagem("999", "501")

        # 1) "polling": chama o núcleo de processamento direto — o mesmo caminho que o
        # poller vai chamar assim que a T3.8 resolver identidade.
        await process_channel_message(
            mensagem,
            agent=agent,
            conversation_service=ConversationService(InMemoryConversationRepository()),
            resolve_deps=_resolve_deps_para(user_id),
            usage_service=_novo_usage_service(),
            max_history_messages=20,
        )

        # 2) "webhook": a mesma mensagem chega pela rota HTTP de verdade.
        concluido = asyncio.Event()

        async def handler(message: ChannelMessage) -> str | None:
            resultado = await process_channel_message(
                message,
                agent=agent,
                conversation_service=ConversationService(InMemoryConversationRepository()),
                resolve_deps=_resolve_deps_para(user_id),
                usage_service=_novo_usage_service(),
                max_history_messages=20,
            )
            concluido.set()
            return resultado

        class _SenderMudo:
            async def send_chat_action(self, chat_id: str, action: str) -> None:
                pass

            async def send_message(self, chat_id: str, text: str) -> None:
                pass

        app = FastAPI()
        app.include_router(
            build_telegram_webhook_router(
                webhook_secret=_SECRET, handler=handler, telegram_client=_SenderMudo()
            )
        )
        update = {
            "update_id": 501,
            "message": {
                "message_id": 501,
                "chat": {"id": 999, "type": "private"},
                "date": 1735000000,
                "text": "gastei 45 no mercado ontem",
            },
        }
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resposta = await client.post(
                f"/webhook/telegram/{_SECRET}", json=update, headers={_HEADER: _SECRET}
            )
            assert resposta.status_code == 200
            await asyncio.wait_for(concluido.wait(), timeout=5.0)

        assert await _total_de_transacoes(user_id) == 1
    finally:
        await _remover_usuario(user_id)
