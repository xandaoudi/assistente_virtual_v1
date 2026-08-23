"""T3.10 — limites de uso e rastreio de custo: conter custo e abuso desde o primeiro dia
(RNF-17, RNF-18)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import UsageLimits

from app.adapters.agent import Deps, create_agent
from app.adapters.channel_message import ChannelMessage
from app.adapters.message_pipeline import process_channel_message
from app.adapters.pipeline_errors import RATE_LIMIT_MESSAGE, safe_message_for
from app.adapters.tools import register_tools
from app.domain.conversation_service import ConversationService
from app.domain.usage_service import RateLimitPolicy, UsageService
from app.models.usage_log import UsageLog
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryConversationRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUsageLogRepository,
    InMemoryUserRepository,
)
from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 23)


def _mensagem(texto: str = "quanto gastei hoje?") -> ChannelMessage:
    return ChannelMessage(
        channel="telegram",
        external_user_id="555",
        text=texto,
        media=None,
        timestamp=datetime.fromtimestamp(1735000000, tz=UTC),
        message_id="1",
    )


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )


def _resolve_deps_para(user_id: uuid.UUID, registry: ToolRegistry):
    async def resolve_deps(message: ChannelMessage) -> Deps:
        return Deps(
            user_id=user_id,
            timezone="America/Sao_Paulo",
            currency="BRL",
            today=_HOJE,
            tools=registry,
        )

    return resolve_deps


_CALL_RESOLVE_DATE = ToolCallPart(
    tool_name="resolve_relative_date", args={"params": {"expression": "hoje"}}
)


@pytest.mark.asyncio
async def test_consumo_e_registrado_apos_cada_execucao() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content="oi")])

    usage_repo = InMemoryUsageLogRepository()
    usage_service = UsageService(usage_repo)
    user_id = uuid.uuid4()
    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)

    await process_channel_message(
        _mensagem(),
        agent=agent,
        conversation_service=ConversationService(InMemoryConversationRepository()),
        resolve_deps=_resolve_deps_para(user_id, _novo_registry()),
        usage_service=usage_service,
        max_history_messages=20,
    )

    registros = await usage_repo.list_by_user(
        user_id, datetime.now(UTC) - timedelta(minutes=1), datetime.now(UTC) + timedelta(minutes=1)
    )
    assert len(registros) == 1
    assert registros[0].requests >= 1
    assert registros[0].input_tokens > 0


@pytest.mark.asyncio
async def test_estourar_teto_de_requisicoes_interrompe_a_execucao_com_erro_tratado() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # Sempre pede uma tool — nunca fecha o turno, forçando mais de uma requisição.
        return ModelResponse(parts=[_CALL_RESOLVE_DATE])

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)

    resposta = await process_channel_message(
        _mensagem(),
        agent=agent,
        conversation_service=ConversationService(InMemoryConversationRepository()),
        resolve_deps=_resolve_deps_para(uuid.uuid4(), _novo_registry()),
        usage_service=UsageService(InMemoryUsageLogRepository()),
        max_history_messages=20,
        usage_limits=UsageLimits(request_limit=1),
    )

    assert resposta == safe_message_for(UsageLimitExceeded("teste"))


@pytest.mark.asyncio
async def test_rate_limit_do_usuario_devolve_mensagem_educada_sem_chamar_a_llm() -> None:
    def roteiro_que_nao_deveria_rodar(
        messages: list[ModelMessage], info: AgentInfo
    ) -> ModelResponse:
        raise AssertionError("rate limit deveria ter impedido a chamada ao modelo")

    user_id = uuid.uuid4()
    usage_repo = InMemoryUsageLogRepository()
    # Uma interação já registrada neste minuto — a próxima mensagem estoura o teto.
    await usage_repo.add(
        UsageLog(
            id=uuid.uuid4(),
            user_id=user_id,
            requests=1,
            input_tokens=10,
            output_tokens=5,
            cache_read_tokens=0,
            cache_write_tokens=0,
            created_at=datetime.now(UTC),
        )
    )
    usage_service = UsageService(usage_repo)
    agent = create_agent(model=FunctionModel(roteiro_que_nao_deveria_rodar))
    register_tools(agent)

    resposta = await process_channel_message(
        _mensagem(),
        agent=agent,
        conversation_service=ConversationService(InMemoryConversationRepository()),
        resolve_deps=_resolve_deps_para(user_id, _novo_registry()),
        usage_service=usage_service,
        max_history_messages=20,
        rate_limit=RateLimitPolicy(messages_per_minute=1, messages_per_day=1000),
    )

    assert resposta == RATE_LIMIT_MESSAGE


@pytest.mark.asyncio
async def test_laco_de_chamadas_de_tool_e_interrompido_pelo_teto() -> None:
    def roteiro_em_laco(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # Sempre chama a mesma tool de novo — sem o teto, isso roda para sempre.
        return ModelResponse(parts=[_CALL_RESOLVE_DATE])

    agent = create_agent(model=FunctionModel(roteiro_em_laco))
    register_tools(agent)

    resposta = await process_channel_message(
        _mensagem(),
        agent=agent,
        conversation_service=ConversationService(InMemoryConversationRepository()),
        resolve_deps=_resolve_deps_para(uuid.uuid4(), _novo_registry()),
        usage_service=UsageService(InMemoryUsageLogRepository()),
        max_history_messages=20,
        usage_limits=UsageLimits(request_limit=100, tool_calls_limit=3),
    )

    assert resposta == safe_message_for(UsageLimitExceeded("teste"))
