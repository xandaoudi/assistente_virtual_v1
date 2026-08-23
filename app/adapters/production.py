"""Monta o pipeline de produção do agente (T3.14): a peça que faltava depois de T3.1-T3.13
— tudo estava testado em isolamento, mas `app/main.py` e `app/telegram_poller.py` ainda
respondiam com um placeholder. Este módulo é o único lugar que liga identidade (T3.8),
histórico (T3.5), degradação (T3.9) e uso/rate limit (T3.10) num `MessageHandler` de verdade.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic_ai.models import Model

from app.adapters.agent import Deps, create_agent
from app.adapters.channel_message import ChannelMessage
from app.adapters.conversation import DEFAULT_AGENT_RUN_TIMEOUT_SECONDS, DEFAULT_USAGE_LIMITS
from app.adapters.message_pipeline import ResolveDeps, idempotency_key_for, process_channel_message
from app.adapters.tools import register_tools
from app.domain.conversation_service import ConversationService
from app.domain.identity_service import IdentityService
from app.domain.repositories import UserRepository
from app.domain.usage_service import RateLimitPolicy, UsageService
from app.repositories.sqlalchemy import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyToolAuditLogRepository,
    SqlAlchemyTransactionRepository,
    SqlAlchemyUsageLogRepository,
    SqlAlchemyUserChannelRepository,
    SqlAlchemyUserRepository,
)
from app.tools.registry import ToolRegistry

MessageHandler = Callable[[ChannelMessage], Awaitable[str | None]]


def build_resolve_deps(
    *,
    identity_service: IdentityService,
    users: UserRepository,
    tools_factory: Callable[[], ToolRegistry],
    channel: str = "telegram",
) -> ResolveDeps:
    """`chat_id` -> `user_id` (T3.8) -> `Deps` com o fuso/moeda reais do usuário — não um
    default fixo, porque `update_user_preferences` (T2) deixa o usuário mudar isso depois."""

    async def resolve_deps(message: ChannelMessage) -> Deps:
        user_id = await identity_service.resolve_user_id(channel, message.external_user_id)
        user = await users.get(user_id)
        if user is None:
            raise RuntimeError(
                f"user_id={user_id} resolvido pela identidade, mas ausente em UserRepository"
            )
        return Deps(
            user_id=user_id,
            timezone=user.timezone,
            currency=user.currency,
            today=datetime.now(ZoneInfo(user.timezone)).date(),
            tools=tools_factory(),
            idempotency_key=idempotency_key_for(message),
        )

    return resolve_deps


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        SqlAlchemyTransactionRepository(),
        SqlAlchemyCategoryRepository(),
        SqlAlchemyUserRepository(),
        SqlAlchemyToolAuditLogRepository(),
    )


def build_production_pipeline(
    *,
    max_history_messages: int,
    model: Model | None = None,
    rate_limit: RateLimitPolicy | None = None,
    timeout_seconds: float = DEFAULT_AGENT_RUN_TIMEOUT_SECONDS,
) -> MessageHandler:
    """Handler real de canal: `ChannelMessage` -> resposta, sobre Postgres de verdade.

    `model=None` usa o Gemini configurado (`create_agent()`); testes passam um
    `FunctionModel` aqui para provar a fiação inteira sem chamar a LLM de verdade (RNF-36).
    """
    agent = create_agent(model=model)
    register_tools(agent)

    conversation_service = ConversationService(SqlAlchemyConversationRepository())
    identity_service = IdentityService(SqlAlchemyUserChannelRepository())
    usage_service = UsageService(SqlAlchemyUsageLogRepository())
    resolve_deps = build_resolve_deps(
        identity_service=identity_service,
        users=SqlAlchemyUserRepository(),
        tools_factory=_novo_registry,
    )

    async def handler(message: ChannelMessage) -> str | None:
        return await process_channel_message(
            message,
            agent=agent,
            conversation_service=conversation_service,
            resolve_deps=resolve_deps,
            usage_service=usage_service,
            max_history_messages=max_history_messages,
            timeout_seconds=timeout_seconds,
            usage_limits=DEFAULT_USAGE_LIMITS,
            rate_limit=rate_limit,
        )

    return handler
