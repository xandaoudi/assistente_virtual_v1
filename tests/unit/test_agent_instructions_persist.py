"""Bug real encontrado na verificação manual da T3.14: o system prompt (T3.2) só valia no
primeiro turno de uma conversa. `Agent(system_prompt=...)` só grava a instrução na primeira
mensagem da história; a partir do segundo turno, `agent.run(message_history=...)` não a
reinjeta — e a higienização da T3.5 (RNF-06) retira de propósito qualquer `SystemPromptPart`
vindo do histórico recarregado, então o agente ficava rodando sem instrução nenhuma a partir
da segunda mensagem. `instructions=` (em vez de `system_prompt=`) resolve isso: o pydantic_ai
recalcula a cada chamada ao modelo, nunca depende do histórico persistido.
"""

import uuid
from datetime import date

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent
from app.adapters.conversation import run_agent_turn
from app.adapters.prompts import load_system_prompt
from app.domain.conversation_service import ConversationService
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryConversationRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 23)


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )


@pytest.mark.asyncio
async def test_o_system_prompt_continua_valendo_a_partir_do_segundo_turno() -> None:
    instrucoes_vistas: list[str | None] = []

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        instrucoes_vistas.append(messages[-1].instructions)
        return ModelResponse(parts=[TextPart(content="ok")])

    agent = create_agent(model=FunctionModel(roteiro))
    conversation_service = ConversationService(InMemoryConversationRepository())
    deps = Deps(
        user_id=uuid.uuid4(),
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=_HOJE,
        tools=_novo_registry(),
    )

    await run_agent_turn(
        agent, deps, conversation_service, "primeira pergunta", max_history_messages=20
    )
    await run_agent_turn(
        agent, deps, conversation_service, "segunda pergunta", max_history_messages=20
    )

    prompt_esperado = load_system_prompt()
    assert instrucoes_vistas[0] == prompt_esperado
    assert instrucoes_vistas[1] == prompt_esperado, (
        "o system prompt sumiu no segundo turno — era exatamente este bug que fez o agente "
        "responder 'Paris' pra 'qual a capital da França?' na verificação manual da T3.14"
    )
