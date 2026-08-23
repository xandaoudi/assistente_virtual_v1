"""Processa uma `ChannelMessage` até uma resposta de texto (RNF-10).

Compartilhado por qualquer canal que já resolveu identidade: o webhook do Telegram (T3.7)
chama isso, e o poller (T3.6) vai chamar a mesma função assim que a T3.8 resolver
`chat_id` -> `user_id`. Não sabe que o Telegram existe — só fala `ChannelMessage` e `Deps`.
"""

from collections.abc import Awaitable, Callable

from pydantic_ai import Agent

from app.adapters.agent import Deps
from app.adapters.channel_message import ChannelMessage
from app.adapters.conversation import run_agent_turn
from app.domain.conversation_service import ConversationService

ResolveDeps = Callable[[ChannelMessage], Awaitable[Deps]]


def idempotency_key_for(message: ChannelMessage) -> str:
    """Chave estável por mensagem — a mesma entrega repetida (retry, polling+webhook)
    produz sempre a mesma chave, para o T2.11 deduplicar na escrita."""
    return f"{message.channel}:{message.message_id}"


async def process_channel_message(
    message: ChannelMessage,
    *,
    agent: Agent[Deps, str],
    conversation_service: ConversationService,
    resolve_deps: ResolveDeps,
    max_history_messages: int,
) -> str | None:
    """`None` quando não há texto para processar — a resposta padrão nesse caso é decisão
    de cada canal (ex.: `app.adapters.telegram.default_reply_for`), não deste módulo."""
    if message.text is None:
        return None

    deps = await resolve_deps(message)
    result = await run_agent_turn(
        agent, deps, conversation_service, message.text, max_history_messages
    )
    return result.output
