"""Processa uma `ChannelMessage` até uma resposta de texto (RNF-10).

Compartilhado por qualquer canal que já resolveu identidade: o webhook do Telegram (T3.7)
chama isso, e o poller (T3.6) vai chamar a mesma função assim que a T3.8 resolver
`chat_id` -> `user_id`. Não sabe que o Telegram existe — só fala `ChannelMessage` e `Deps`.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from app.adapters.agent import Deps
from app.adapters.channel_message import ChannelMessage
from app.adapters.conversation import (
    DEFAULT_AGENT_RUN_TIMEOUT_SECONDS,
    DEFAULT_USAGE_LIMITS,
    run_agent_turn,
)
from app.adapters.pipeline_errors import RATE_LIMIT_MESSAGE, safe_message_for
from app.domain.conversation_service import ConversationService
from app.domain.usage_service import RateLimitPolicy, UsageService

logger = logging.getLogger(__name__)

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
    usage_service: UsageService,
    timeout_seconds: float = DEFAULT_AGENT_RUN_TIMEOUT_SECONDS,
    usage_limits: UsageLimits = DEFAULT_USAGE_LIMITS,
    rate_limit: RateLimitPolicy | None = None,
) -> str | None:
    """`None` quando não há texto para processar — a resposta padrão nesse caso é decisão
    de cada canal (ex.: `app.adapters.telegram.default_reply_for`), não deste módulo.

    T3.9/RF-71/RNF-16: nenhuma falha daqui para cima — LLM indisponível, timeout, limite de
    uso, banco indisponível, o que for — chega ao usuário como exceção crua. `safe_message_for`
    sempre devolve uma mensagem pronta em português; o erro real só vai para o log.

    T3.10/RF-17: `rate_limit`, quando informado, é checado *antes* de tocar o agente — estourar
    o teto nunca chama a LLM. Toda execução bem-sucedida grava seu consumo via `usage_service`
    (RNF-18), o que também alimenta a próxima checagem de rate limit.
    """
    if message.text is None:
        return None

    try:
        deps = await resolve_deps(message)

        if rate_limit is not None and await usage_service.exceeds_rate_limit(
            deps.user_id, rate_limit, now=datetime.now(UTC)
        ):
            return RATE_LIMIT_MESSAGE

        result = await run_agent_turn(
            agent,
            deps,
            conversation_service,
            message.text,
            max_history_messages,
            timeout_seconds=timeout_seconds,
            usage_limits=usage_limits,
        )
        await usage_service.record(
            deps.user_id,
            requests=result.usage.requests,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cache_read_tokens=result.usage.cache_read_tokens,
            cache_write_tokens=result.usage.cache_write_tokens,
        )
        return result.output
    except Exception as erro:
        logger.exception("falha ao processar mensagem do canal: channel=%s", message.channel)
        return safe_message_for(erro)
