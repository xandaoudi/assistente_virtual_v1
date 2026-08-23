"""Serialização do histórico de conversa e orquestração de um turno do agente (T3.5, RF-65).

`app.domain` nunca vê um `ModelMessage` do Pydantic AI (RF-86) — só dicts JSON-seguros. A
conversão para os tipos reais do framework, e a higienização de histórico vindo de uma
fonte que este processo não controlou por completo (RNF-06: um `SystemPromptPart` gravado
num turno anterior não deve valer como instrução hoje), moram aqui.
"""

from pydantic_ai import Agent
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, sanitize_messages

from app.adapters.agent import Deps
from app.domain.conversation_service import ConversationService


def serialize_messages(messages: list[ModelMessage]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    return result


def deserialize_messages(raw: list[dict[str, object]]) -> list[ModelMessage]:
    mensagens = ModelMessagesTypeAdapter.validate_python(raw)
    return sanitize_messages(mensagens)


async def run_agent_turn(
    agent: Agent[Deps, str],
    deps: Deps,
    conversation_service: ConversationService,
    user_text: str,
    max_history_messages: int,
) -> AgentRunResult[str]:
    """Carrega o histórico da janela, roda o agente e grava só as mensagens novas do turno."""
    historico_bruto = await conversation_service.load_recent_history(
        deps.user_id, max_history_messages
    )
    historico = deserialize_messages(historico_bruto)

    result = await agent.run(user_text, deps=deps, message_history=historico)

    novas_mensagens = serialize_messages(result.new_messages())
    await conversation_service.append_messages(deps.user_id, novas_mensagens)
    return result
