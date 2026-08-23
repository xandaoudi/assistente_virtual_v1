"""T3.9 — degradação e tratamento de erro: falhar de forma compreensível, sem vazar
detalhe interno e sem perder uma operação já confirmada (RF-71, RNF-16)."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

import pytest
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent
from app.adapters.channel_message import ChannelMessage
from app.adapters.message_pipeline import process_channel_message
from app.adapters.pipeline_errors import OperationConfirmedResponseFailedError, safe_message_for
from app.adapters.tools import register_tools
from app.domain.conversation_service import ConversationService
from app.models.transaction import Transaction
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

_RoteiroFn = Callable[[list[ModelMessage], AgentInfo], ModelResponse | Awaitable[ModelResponse]]


def _mensagem(message_id: str = "1", texto: str = "gastei 45 no mercado") -> ChannelMessage:
    return ChannelMessage(
        channel="telegram",
        external_user_id="555",
        text=texto,
        media=None,
        timestamp=datetime.fromtimestamp(1735000000, tz=UTC),
        message_id=message_id,
    )


def _novo_registry(
    transaction_repo: InMemoryTransactionRepository | None = None,
) -> ToolRegistry:
    return ToolRegistry(
        transaction_repo or InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )


def _resolve_deps_para(user_id: uuid.UUID, registry: ToolRegistry) -> Callable[..., object]:
    async def resolve_deps(message: ChannelMessage) -> Deps:
        return Deps(
            user_id=user_id,
            timezone="America/Sao_Paulo",
            currency="BRL",
            today=_HOJE,
            tools=registry,
        )

    return resolve_deps


async def _processa(
    roteiro: _RoteiroFn,
    registry: ToolRegistry,
    user_id: uuid.UUID,
    *,
    timeout_seconds: float = 20.0,
) -> str | None:
    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    return await process_channel_message(
        _mensagem(),
        agent=agent,
        conversation_service=ConversationService(InMemoryConversationRepository()),
        resolve_deps=_resolve_deps_para(user_id, registry),
        max_history_messages=20,
        timeout_seconds=timeout_seconds,
    )


_CALL_CRIA_TRANSACAO = ToolCallPart(
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


@pytest.mark.asyncio
async def test_llm_indisponivel_gera_mensagem_clara_sem_stack_trace() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=503, model_name="gemini-teste", body="indisponível")

    resposta = await _processa(roteiro, _novo_registry(), uuid.uuid4())

    assert resposta == safe_message_for(ModelHTTPError(status_code=503, model_name="x"))
    assert resposta is not None
    assert "Traceback" not in resposta
    assert "503" not in resposta
    assert "ModelHTTPError" not in resposta


@pytest.mark.asyncio
async def test_timeout_gera_mensagem_propria_diferente_do_erro_generico() -> None:
    async def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(2.0)
        return ModelResponse(parts=[TextPart(content="nunca chega aqui")])

    resposta = await _processa(roteiro, _novo_registry(), uuid.uuid4(), timeout_seconds=0.05)

    assert resposta == safe_message_for(TimeoutError())
    assert resposta != safe_message_for(RuntimeError("erro qualquer"))


@pytest.mark.asyncio
async def test_tool_com_erro_interno_nao_expoe_detalhe_ao_usuario() -> None:
    transaction_repo = InMemoryTransactionRepository()

    async def _add_com_falha(user_id: uuid.UUID, transaction: Transaction) -> Transaction:
        raise RuntimeError(
            'duplicate key value violates unique constraint "transactions_pkey" '
            'table "transactions" — sqlalchemy.exc.IntegrityError'
        )

    transaction_repo.add = _add_com_falha  # type: ignore[method-assign]
    registry = _novo_registry(transaction_repo)

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[_CALL_CRIA_TRANSACAO])
        return ModelResponse(parts=[TextPart(content="Desculpe, não consegui registrar agora.")])

    resposta = await _processa(roteiro, registry, uuid.uuid4())

    assert resposta == "Desculpe, não consegui registrar agora."
    for proibido in ("Traceback", "sqlalchemy", "transactions_pkey", "IntegrityError"):
        assert proibido not in (resposta or "")


def test_safe_message_for_nunca_expoe_traceback_sqlalchemy_ou_tabela() -> None:
    erros: list[Exception] = [
        ModelHTTPError(status_code=503, model_name="gemini-teste"),
        TimeoutError(),
        UsageLimitExceeded("limite de tokens estourado"),
        OperationConfirmedResponseFailedError(),
        RuntimeError(
            "Traceback (most recent call last): sqlalchemy.exc.OperationalError: "
            'relation "transactions" does not exist'
        ),
    ]

    for erro in erros:
        mensagem = safe_message_for(erro)
        for proibido in ("Traceback", "sqlalchemy", "transactions", "OperationalError"):
            assert proibido not in mensagem, f"{erro!r} vazou detalhe: {mensagem!r}"


@pytest.mark.asyncio
async def test_transacao_confirmada_mais_falha_na_resposta_informa_sucesso_ao_usuario() -> None:
    transaction_repo = InMemoryTransactionRepository()
    registry = _novo_registry(transaction_repo)
    user_id = uuid.uuid4()

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[_CALL_CRIA_TRANSACAO])
        # A tool já confirmou a transação (ToolReturnPart de sucesso no histórico) — é aqui
        # que a "redação da resposta" falha, depois do lançamento gravado.
        raise ModelHTTPError(status_code=503, model_name="gemini-teste")

    resposta = await _processa(roteiro, registry, user_id)

    assert resposta == safe_message_for(OperationConfirmedResponseFailedError())
    assert resposta != safe_message_for(ModelHTTPError(status_code=503, model_name="x"))

    transacoes = await transaction_repo.list_by_user(user_id)
    assert len(transacoes) == 1
    assert str(transacoes[0].amount) == "45.00"
