"""Serialização do histórico de conversa e orquestração de um turno do agente (T3.5, RF-65).

`app.domain` nunca vê um `ModelMessage` do Pydantic AI (RF-86) — só dicts JSON-seguros. A
conversão para os tipos reais do framework, e a higienização de histórico vindo de uma
fonte que este processo não controlou por completo (RNF-06: um `SystemPromptPart` gravado
num turno anterior não deve valer como instrução hoje), moram aqui.
"""

import asyncio

from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, sanitize_messages
from pydantic_ai.usage import UsageLimits

from app.adapters.agent import Deps
from app.adapters.pipeline_errors import (
    OperationConfirmedResponseFailedError,
    write_operation_succeeded,
)
from app.domain.conversation_service import ConversationService

DEFAULT_AGENT_RUN_TIMEOUT_SECONDS = 20.0

# T3.10/RNF-17: sem teto, um agente preso num laço de chamadas de tool queima cota até
# alguém perceber. `tool_calls_limit` é a defesa direta contra esse laço; `request_limit`
# contém o caso vizinho (idas e vindas de retry sem fim).
DEFAULT_USAGE_LIMITS = UsageLimits(request_limit=15, tool_calls_limit=10)


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
    timeout_seconds: float = DEFAULT_AGENT_RUN_TIMEOUT_SECONDS,
    usage_limits: UsageLimits = DEFAULT_USAGE_LIMITS,
) -> AgentRunResult[str]:
    """Carrega o histórico da janela, roda o agente e grava só as mensagens novas do turno.

    RNF-13/RNF-12: `timeout_seconds` garante que uma LLM travada nunca segura o turno para
    sempre. RF-71/RNF-16 (T3.9): se o turno falhar depois de uma tool de escrita já ter
    confirmado a operação — a redação da resposta, por exemplo —, o erro que sobe é
    `OperationConfirmedResponseFailedError`, não o erro original: quem chama nunca deve tratar
    essa falha como se nada tivesse sido gravado. RNF-17 (T3.10): `usage_limits` é o teto de
    requisições/chamadas de tool por execução — estourá-lo levanta `UsageLimitExceeded`
    (já traduzido por `pipeline_errors.safe_message_for`).
    """
    historico_bruto = await conversation_service.load_recent_history(
        deps.user_id, max_history_messages
    )
    historico = deserialize_messages(historico_bruto)

    with capture_run_messages() as mensagens_capturadas:
        try:
            result = await asyncio.wait_for(
                agent.run(
                    user_text, deps=deps, message_history=historico, usage_limits=usage_limits
                ),
                timeout=timeout_seconds,
            )
        except Exception as erro:
            if write_operation_succeeded(mensagens_capturadas):
                raise OperationConfirmedResponseFailedError() from erro
            raise

    novas_mensagens = serialize_messages(result.new_messages())
    await conversation_service.append_messages(deps.user_id, novas_mensagens)
    return result
