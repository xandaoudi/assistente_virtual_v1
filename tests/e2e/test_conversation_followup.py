"""T3.5 — CA-09: "e no mês passado?" é entendido como follow-up do histórico persistido."""

import uuid
from datetime import date

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent
from app.adapters.conversation import run_agent_turn
from app.adapters.tools import register_tools
from app.domain.conversation_service import ConversationService
from app.domain.enums import TransactionType
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryConversationRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.schemas import CreateTransactionParams

pytestmark = pytest.mark.e2e

_HOJE = date(2026, 8, 23)
_INICIO_MES_ATUAL = date(2026, 8, 1)
_FIM_MES_ATUAL = date(2026, 8, 31)
_INICIO_MES_PASSADO = date(2026, 7, 1)
_FIM_MES_PASSADO = date(2026, 7, 31)


def _ctx(user_id: uuid.UUID) -> ToolContext:
    return ToolContext(user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_HOJE)


@pytest.mark.asyncio
async def test_segunda_pergunta_e_entendida_como_followup_do_historico_persistido() -> None:
    registry = ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )
    user_id = uuid.uuid4()
    await registry.create_transaction(
        _ctx(user_id),
        CreateTransactionParams(
            type=TransactionType.EXPENSE, amount="45,00", description="Mercado", date=_HOJE
        ),
    )
    await registry.create_transaction(
        _ctx(user_id),
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="30,00",
            description="Farmácia",
            date=date(2026, 7, 15),
        ),
    )

    chamadas: list[list[ModelMessage]] = []

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        chamadas.append(list(messages))
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_summary",
                        args={
                            "params": {
                                "start_date": str(_INICIO_MES_ATUAL),
                                "end_date": str(_FIM_MES_ATUAL),
                            }
                        },
                    )
                ]
            )
        if len(messages) == 3:
            return ModelResponse(parts=[TextPart(content="Você gastou R$ 45,00 este mês.")])
        if len(messages) == 5:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_summary",
                        args={
                            "params": {
                                "start_date": str(_INICIO_MES_PASSADO),
                                "end_date": str(_FIM_MES_PASSADO),
                            }
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="No mês passado você gastou R$ 30,00.")])

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    conversation_service = ConversationService(InMemoryConversationRepository())
    deps = Deps(
        user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_HOJE, tools=registry
    )

    resultado_1 = await run_agent_turn(
        agent, deps, conversation_service, "quanto gastei esse mês?", max_history_messages=20
    )
    resultado_2 = await run_agent_turn(
        agent, deps, conversation_service, "e no mês passado?", max_history_messages=20
    )

    assert resultado_1.output == "Você gastou R$ 45,00 este mês."
    assert resultado_2.output == "No mês passado você gastou R$ 30,00."

    # CA-09: a segunda chamada ao modelo já chega com a primeira pergunta no histórico —
    # prova que ele veio do que foi persistido e recarregado (run_agent_turn de novo, do
    # zero), não de estado em memória de um único agent.run().
    assert len(chamadas) == 4
    primeira_chamada_do_segundo_turno = chamadas[2]
    assert any(
        getattr(part, "content", None) == "quanto gastei esse mês?"
        for message in primeira_chamada_do_segundo_turno
        for part in message.parts
    )


@pytest.mark.asyncio
async def test_janela_limita_o_que_e_reenviado_ao_modelo_no_turno_seguinte() -> None:
    registry = ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )
    user_id = uuid.uuid4()

    tamanhos_recebidos: list[int] = []

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tamanhos_recebidos.append(len(messages))
        return ModelResponse(parts=[TextPart(content="ok")])

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    conversation_service = ConversationService(InMemoryConversationRepository())
    deps = Deps(
        user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_HOJE, tools=registry
    )

    for numero in range(5):
        await run_agent_turn(
            agent, deps, conversation_service, f"mensagem {numero}", max_history_messages=2
        )

    # Cada turno sem tool call grava 2 mensagens (pedido + resposta); com a janela em 2, o
    # próximo turno nunca recebe mais que a última rodada — não cresce a cada iteração.
    assert tamanhos_recebidos == [1, 3, 3, 3, 3]
