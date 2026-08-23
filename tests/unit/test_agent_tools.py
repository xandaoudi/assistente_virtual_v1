"""Registro automático das tools do registry no agente e tradução do envelope (T3.4)."""

import uuid
from datetime import date

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.adapters.agent import Deps, create_agent
from app.adapters.tools import register_tools, registry_tool_methods, translate_tool_error
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.audit import audited
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.results import ErrorCode, ToolError, ToolResult, ToolSuccess
from app.tools.schemas import GetSummaryParams

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 23)
_MENSAGEM_ERRO_INTERNO = "Erro interno inesperado. Tente novamente mais tarde."


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )


def _deps() -> Deps:
    return Deps(
        user_id=uuid.uuid4(),
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=_HOJE,
        tools=_novo_registry(),
    )


async def _nomes_registrados(agent: Agent[Deps, str]) -> set[str]:
    await agent.run("oi", deps=_deps())
    return {t.name for t in agent.model.last_model_request_parameters.function_tools}  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Registro automático
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_todas_as_tools_do_registry_ficam_registradas_no_agente() -> None:
    agent = create_agent(model=TestModel(call_tools=[]))
    register_tools(agent)

    nomes_esperados = {nome for nome, _ in registry_tool_methods()}
    nomes_registrados = await _nomes_registrados(agent)

    assert nomes_registrados == nomes_esperados
    assert nomes_registrados, "nenhuma tool foi registrada — teste não prova nada"


@pytest.mark.asyncio
async def test_uma_tool_nova_no_registry_aparece_automaticamente_sem_lista_duplicada() -> None:
    class _RegistryComToolExtra(ToolRegistry):
        @audited("tool_nova_de_teste")
        async def tool_nova_de_teste(
            self, ctx: ToolContext, params: GetSummaryParams
        ) -> ToolResult[str]:
            return ToolSuccess(data="ok")

    agent_original = create_agent(model=TestModel(call_tools=[]))
    register_tools(agent_original)
    nomes_originais = await _nomes_registrados(agent_original)

    agent_estendido = create_agent(model=TestModel(call_tools=[]))
    register_tools(agent_estendido, registry_cls=_RegistryComToolExtra)
    nomes_estendidos = await _nomes_registrados(agent_estendido)

    assert nomes_estendidos == nomes_originais | {"tool_nova_de_teste"}
    assert len(nomes_estendidos) == len(nomes_originais) + 1  # sem duplicação


# ---------------------------------------------------------------------------
# Tradução do envelope T2.1 -> mensagem para o modelo
# ---------------------------------------------------------------------------


def test_cada_codigo_de_erro_vira_a_mensagem_correta_para_o_modelo() -> None:
    ambiguo = ToolError(code=ErrorCode.AMBIGUOUS_INPUT, message='O valor "1.250" é ambíguo.')
    mensagem_ambigua = translate_tool_error(ambiguo)
    assert 'O valor "1.250" é ambíguo.' in mensagem_ambigua
    assert "pergunte" in mensagem_ambigua.lower()

    violacao = ToolError(code=ErrorCode.BUSINESS_RULE_VIOLATION, message="Categoria já existe.")
    assert translate_tool_error(violacao) == "Categoria já existe."

    nao_encontrado = ToolError(code=ErrorCode.NOT_FOUND, message="Transação não encontrada.")
    assert translate_tool_error(nao_encontrado) == "Transação não encontrada."

    erro_interno = ToolError(code=ErrorCode.INTERNAL_ERROR, message=_MENSAGEM_ERRO_INTERNO)
    assert translate_tool_error(erro_interno) == _MENSAGEM_ERRO_INTERNO


def test_internal_error_nao_vaza_detalhe_interno_mesmo_que_a_mensagem_vaze() -> None:
    # Segunda barreira, independente do run_safely (Etapa 2): mesmo que uma mensagem de
    # INTERNAL_ERROR viesse com detalhe interno, a tradução nunca repassa — sempre troca
    # pelo texto genérico, ignorando o conteúdo original.
    erro_com_vazamento = ToolError(
        code=ErrorCode.INTERNAL_ERROR,
        message='Traceback: psycopg.errors.UndefinedTable: relation "transactions" '
        "does not exist\nSELECT * FROM transactions WHERE user_id = ...",
    )

    mensagem = translate_tool_error(erro_com_vazamento)

    assert mensagem == _MENSAGEM_ERRO_INTERNO
    for termo_proibido in ("traceback", "psycopg", "transactions", "select"):
        assert termo_proibido not in mensagem.lower()


@pytest.mark.asyncio
async def test_erro_traduzido_chega_ao_modelo_atraves_do_agente_de_verdade() -> None:
    # Prova que translate_tool_error não é só uma função pura solta: está de fato ligada
    # ao caminho de execução real da tool através do agente.
    def responder(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="create_transaction",
                        args={
                            "params": {
                                "type": "expense",
                                "amount": "1.250",
                                "description": "Mercado",
                            }
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="ok")])

    agent = create_agent(model=FunctionModel(responder))
    register_tools(agent)

    result = await agent.run("gastei 1.250 no mercado", deps=_deps())

    tool_return = next(
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    assert "ambíguo" in tool_return.content.lower()
    assert "pergunte" in tool_return.content.lower()
