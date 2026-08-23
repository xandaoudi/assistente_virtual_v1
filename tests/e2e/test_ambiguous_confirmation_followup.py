"""T3.11 — fluxo de confirmação para entrada ambígua (RF-35, RF-66).

`AMBIGUOUS_INPUT` (Etapa 2) já vira uma pergunta em vez de erro genérico (T3.4), e a
`test_valor_ambiguo_nao_cria_transacao_e_pede_esclarecimento` em
`test_agent_pipeline_regression.py` já prova isso dentro de uma única execução do agente.
O que falta cobrir é o que só aparece entre dois turnos, com o histórico persistido da T3.5:
a resposta do usuário completando o lançamento, e — o critério de aceite da tarefa — o
usuário ignorando a pergunta sem deixar nada pendente gravado sozinho depois.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent
from app.adapters.conversation import run_agent_turn
from app.adapters.tools import register_tools
from app.domain.conversation_service import ConversationService
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryConversationRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.e2e

_HOJE = date(2026, 8, 23)

_CALL_VALOR_AMBIGUO = ToolCallPart(
    tool_name="create_transaction",
    args={
        "params": {
            "type": "expense",
            "amount": "1.250",
            "description": "Mercado",
            "date": str(_HOJE),
        }
    },
)
_PERGUNTA_DE_ESCLARECIMENTO = "1.250 é mil e duzentos e cinquenta ou 1 real e 25 centavos?"


def _novo_registry() -> tuple[ToolRegistry, InMemoryTransactionRepository]:
    transacoes = InMemoryTransactionRepository()
    registry = ToolRegistry(
        transacoes,
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )
    return registry, transacoes


@pytest.mark.asyncio
async def test_resposta_do_usuario_no_turno_seguinte_completa_a_gravacao_com_valor_certo() -> None:
    registry, transacoes = _novo_registry()

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # Turno 1: valor ambíguo -> a tool falha -> o agente pergunta, sem gravar nada.
        if len(messages) == 1:
            return ModelResponse(parts=[_CALL_VALOR_AMBIGUO])
        if len(messages) == 3:
            return ModelResponse(parts=[TextPart(content=_PERGUNTA_DE_ESCLARECIMENTO)])

        # Turno 2: a resposta do usuário desambiguou o valor -> a tool completa a gravação.
        if len(messages) == 5:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="create_transaction",
                        args={
                            "params": {
                                "type": "expense",
                                "amount": "1.250,00",
                                "description": "Mercado",
                                "date": str(_HOJE),
                            }
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="Registrei R$ 1.250,00 no mercado.")])

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    conversation_service = ConversationService(InMemoryConversationRepository())
    deps = Deps(
        user_id=uuid.uuid4(),
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=_HOJE,
        tools=registry,
    )
    user_id = deps.user_id

    resultado_1 = await run_agent_turn(
        agent, deps, conversation_service, "gastei 1.250 no mercado", max_history_messages=20
    )
    assert resultado_1.output == _PERGUNTA_DE_ESCLARECIMENTO
    assert await transacoes.list_by_user(user_id) == []

    resultado_2 = await run_agent_turn(
        agent, deps, conversation_service, "1.250,00", max_history_messages=20
    )
    assert resultado_2.output == "Registrei R$ 1.250,00 no mercado."

    persistidas = await transacoes.list_by_user(user_id)
    assert len(persistidas) == 1
    assert persistidas[0].amount == Decimal("1250.00")


@pytest.mark.asyncio
async def test_usuario_ignorando_a_pergunta_e_mudando_de_assunto_nao_deixa_pendente_gravado() -> (
    None
):
    registry, transacoes = _novo_registry()

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[_CALL_VALOR_AMBIGUO])
        if len(messages) == 3:
            return ModelResponse(parts=[TextPart(content=_PERGUNTA_DE_ESCLARECIMENTO)])

        # Turno 2: o usuário ignora a pergunta e muda de assunto — nenhuma tool é chamada,
        # muito menos create_transaction com um valor chutado.
        return ModelResponse(
            parts=[
                TextPart(content="Isso foge do meu escopo — posso ajudar com finanças e agenda!")
            ]
        )

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    conversation_service = ConversationService(InMemoryConversationRepository())
    deps = Deps(
        user_id=uuid.uuid4(),
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=_HOJE,
        tools=registry,
    )

    resultado_1 = await run_agent_turn(
        agent, deps, conversation_service, "gastei 1.250 no mercado", max_history_messages=20
    )
    assert resultado_1.output == _PERGUNTA_DE_ESCLARECIMENTO
    assert await transacoes.list_by_user(deps.user_id) == []

    resultado_2 = await run_agent_turn(
        agent,
        deps,
        conversation_service,
        "qual a capital da França?",
        max_history_messages=20,
    )
    assert resultado_2.output == "Isso foge do meu escopo — posso ajudar com finanças e agenda!"

    # O critério de aceite da T3.11: confirmação pendente não grava sozinha depois.
    assert await transacoes.list_by_user(deps.user_id) == []
