"""Regressão do pipeline do agente (T3.1-T3.4) — modelo, prompt, `Deps` e tools reais
ligados de ponta a ponta.

Não chama a LLM de verdade (RNF-36) — usa `FunctionModel`/`TestModel` com um roteiro
determinístico, mas não atalha nenhuma outra peça: `create_agent()` real (modelo por
config, prompt do arquivo versionado), `register_tools()` com o catálogo inteiro, e
`ToolRegistry` real sobre repositórios em memória. Se alguém quebrar a fiação entre essas
peças, é aqui que aparece — sem precisar de credencial nem rede.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.adapters.agent import Deps, create_agent
from app.adapters.tools import register_tools, registry_tool_methods
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.e2e

_HOJE = date(2026, 8, 23)


def _novo_registry() -> tuple[ToolRegistry, InMemoryTransactionRepository]:
    transacoes = InMemoryTransactionRepository()
    registry = ToolRegistry(
        transacoes,
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )
    return registry, transacoes


def _deps(tools: ToolRegistry) -> Deps:
    return Deps(
        user_id=uuid.uuid4(),
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=_HOJE,
        tools=tools,
    )


def _tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)
    ]


@pytest.mark.asyncio
async def test_todo_o_catalogo_de_tools_fica_registrado_sem_expor_user_id() -> None:
    agent = create_agent(model=TestModel(call_tools=[]))
    register_tools(agent)
    registry, _ = _novo_registry()

    await agent.run("oi", deps=_deps(registry))

    tool_defs = agent.model.last_model_request_parameters.function_tools  # type: ignore[union-attr]
    nomes_esperados = {nome for nome, _ in registry_tool_methods()}

    assert {t.name for t in tool_defs} == nomes_esperados
    for tool_def in tool_defs:
        assert "user_id" not in str(tool_def.parameters_json_schema), tool_def.name


@pytest.mark.asyncio
async def test_fluxo_criar_despesa_e_consultar_resumo_de_ponta_a_ponta() -> None:
    """ "gastei 45 no mercado hoje" seguido de "quanto gastei esse mês?", com o agente real."""

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
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
                ]
            )
        if len(messages) == 3:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_summary",
                        args={"params": {"start_date": str(_HOJE), "end_date": str(_HOJE)}},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="Você gastou R$ 45,00 este mês.")])

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, transacoes = _novo_registry()
    deps = _deps(registry)

    result = await agent.run("gastei 45 no mercado hoje", deps=deps)

    retornos = _tool_returns(result.all_messages())
    assert len(retornos) == 2
    criada, resumo = retornos[0].content, retornos[1].content
    assert criada.amount == Decimal("45.00")  # create_transaction devolveu a transação criada
    assert resumo.total_expenses == Decimal("45.00")  # get_summary reflete a despesa recém-criada
    assert result.output == "Você gastou R$ 45,00 este mês."

    persistidas = await transacoes.list_by_user(deps.user_id)
    assert len(persistidas) == 1
    assert persistidas[0].amount == Decimal("45.00")


@pytest.mark.asyncio
async def test_valor_ambiguo_nao_cria_transacao_e_pede_esclarecimento() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
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
        return ModelResponse(
            parts=[TextPart(content="1.250 é mil e duzentos e cinquenta ou 1,25?")]
        )

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, transacoes = _novo_registry()
    deps = _deps(registry)

    result = await agent.run("gastei 1.250 no mercado", deps=deps)

    retornos = _tool_returns(result.all_messages())
    assert len(retornos) == 1
    assert "ambíguo" in retornos[0].content.lower()
    assert "pergunte" in retornos[0].content.lower()

    persistidas = await transacoes.list_by_user(deps.user_id)
    assert persistidas == []


@pytest.mark.asyncio
async def test_transacao_inexistente_e_tratada_com_mensagem_segura() -> None:
    id_inexistente = uuid.uuid4()

    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="delete_transaction",
                        args={"params": {"transaction_id": str(id_inexistente)}},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="não encontrei essa transação")])

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, _ = _novo_registry()
    deps = _deps(registry)

    result = await agent.run("apaga aquela transação", deps=deps)

    retornos = _tool_returns(result.all_messages())
    assert len(retornos) == 1
    assert retornos[0].content == "Transação não encontrada."
    for termo_proibido in (str(id_inexistente), "traceback", "sqlalchemy", "sql"):
        assert termo_proibido.lower() not in retornos[0].content.lower()
