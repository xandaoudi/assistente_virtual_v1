"""T3.12 — testes de comportamento do agente (RNF-37): frase -> tool esperada + parâmetros
esperados, verificando o que o agente **decidiu** (via `capture_run_messages()`), não só o
que respondeu.

RNF-35/RNF-36: o modelo é sempre `FunctionModel`, roteirizado por caso — isso prova que a
fiação (schema -> tool -> domínio -> banco) está correta para cada forma de chamada. Não
prova, e não tenta provar, que o Gemini de verdade escolhe essa tool para essa frase em
português: essa é a pergunta da T3.13, com o modelo real, fora do portão de merge.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent
from app.adapters.llm import build_llm_model
from app.adapters.tools import register_tools
from app.core.config import Settings
from app.domain.enums import TransactionType
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.schemas import CreateCategoryParams, CreateTransactionParams

pytestmark = pytest.mark.e2e

_HOJE = date(2026, 8, 23)
_ONTEM = _HOJE - timedelta(days=1)
_INICIO_MES = date(2026, 8, 1)
_FIM_MES = date(2026, 8, 31)
_INICIO_JULHO = date(2026, 7, 1)
_FIM_JULHO = date(2026, 7, 31)


def _novo_registry() -> tuple[
    ToolRegistry, InMemoryTransactionRepository, InMemoryCategoryRepository
]:
    transacoes = InMemoryTransactionRepository()
    categorias = InMemoryCategoryRepository()
    registry = ToolRegistry(
        transacoes, categorias, InMemoryUserRepository(), InMemoryToolAuditLogRepository()
    )
    return registry, transacoes, categorias


def _deps(tools: ToolRegistry, user_id: uuid.UUID) -> Deps:
    return Deps(
        user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_HOJE, tools=tools
    )


def _ctx(user_id: uuid.UUID) -> ToolContext:
    return ToolContext(user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_HOJE)


def _tool_calls(messages: list[ModelMessage]) -> list[ToolCallPart]:
    return [
        part for message in messages for part in message.parts if isinstance(part, ToolCallPart)
    ]


def _tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)
    ]


def _resposta_final(roteiro_ultima_fala: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=roteiro_ultima_fala)])


@pytest.mark.asyncio
async def test_gastei_45_no_mercado_ontem_decide_create_transaction_expense() -> None:
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
                                "date": str(_ONTEM),
                            }
                        },
                    )
                ]
            )
        return _resposta_final("Registrei R$ 45,00 no mercado, ontem.")

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, transacoes, _ = _novo_registry()
    deps = _deps(registry, uuid.uuid4())

    with capture_run_messages() as mensagens:
        await agent.run("gastei 45 no mercado ontem", deps=deps)

    chamadas = _tool_calls(mensagens)
    assert len(chamadas) == 1
    assert chamadas[0].tool_name == "create_transaction"
    params = chamadas[0].args_as_dict()["params"]
    assert params["type"] == "expense"
    assert params["amount"] == "45,00"
    assert params["date"] == str(_ONTEM)

    persistidas = await transacoes.list_by_user(deps.user_id)
    assert len(persistidas) == 1
    assert persistidas[0].type == TransactionType.EXPENSE
    assert persistidas[0].amount == Decimal("45.00")
    assert persistidas[0].date == _ONTEM


@pytest.mark.asyncio
async def test_recebi_3200_de_salario_hoje_decide_create_transaction_income() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="create_transaction",
                        args={
                            "params": {
                                "type": "income",
                                "amount": "3200,00",
                                "description": "Salário",
                                "date": str(_HOJE),
                            }
                        },
                    )
                ]
            )
        return _resposta_final("Registrei R$ 3.200,00 de salário, hoje.")

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, transacoes, _ = _novo_registry()
    deps = _deps(registry, uuid.uuid4())

    with capture_run_messages() as mensagens:
        await agent.run("recebi 3200 de salário hoje", deps=deps)

    chamadas = _tool_calls(mensagens)
    assert len(chamadas) == 1
    assert chamadas[0].tool_name == "create_transaction"
    params = chamadas[0].args_as_dict()["params"]
    assert params["type"] == "income"
    assert params["amount"] == "3200,00"
    assert params["date"] == str(_HOJE)

    persistidas = await transacoes.list_by_user(deps.user_id)
    assert len(persistidas) == 1
    assert persistidas[0].type == TransactionType.INCOME
    assert persistidas[0].amount == Decimal("3200.00")
    assert persistidas[0].date == _HOJE


@pytest.mark.asyncio
async def test_quanto_gastei_esse_mes_decide_get_summary_do_mes_corrente() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_summary",
                        args={
                            "params": {
                                "start_date": str(_INICIO_MES),
                                "end_date": str(_FIM_MES),
                            }
                        },
                    )
                ]
            )
        return _resposta_final("Você gastou R$ 45,00 este mês.")

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, _, _ = _novo_registry()
    deps = _deps(registry, uuid.uuid4())
    await registry.create_transaction(
        _ctx(deps.user_id),
        CreateTransactionParams(
            type=TransactionType.EXPENSE, amount="45,00", description="Mercado", date=_HOJE
        ),
    )

    with capture_run_messages() as mensagens:
        await agent.run("quanto gastei esse mês?", deps=deps)

    chamadas = _tool_calls(mensagens)
    assert len(chamadas) == 1
    assert chamadas[0].tool_name == "get_summary"
    params = chamadas[0].args_as_dict()["params"]
    assert params["start_date"] == str(_INICIO_MES)
    assert params["end_date"] == str(_FIM_MES)

    retorno = _tool_returns(mensagens)[0].content
    assert retorno.total_expenses == Decimal("45.00")


@pytest.mark.asyncio
async def test_quanto_gastei_com_transporte_em_julho_decide_get_category_spending() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_category_spending",
                        args={
                            "params": {
                                "start_date": str(_INICIO_JULHO),
                                "end_date": str(_FIM_JULHO),
                                "category": "Transporte",
                            }
                        },
                    )
                ]
            )
        return _resposta_final("Você gastou R$ 80,00 com transporte em julho.")

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, _, _ = _novo_registry()
    deps = _deps(registry, uuid.uuid4())
    ctx = _ctx(deps.user_id)
    await registry.create_category(
        ctx, CreateCategoryParams(name="Transporte", type=TransactionType.EXPENSE)
    )
    await registry.create_transaction(
        ctx,
        CreateTransactionParams(
            type=TransactionType.EXPENSE,
            amount="80,00",
            description="Ônibus",
            date=date(2026, 7, 10),
            category="Transporte",
        ),
    )

    with capture_run_messages() as mensagens:
        await agent.run("quanto gastei com transporte em julho?", deps=deps)

    chamadas = _tool_calls(mensagens)
    assert len(chamadas) == 1
    assert chamadas[0].tool_name == "get_category_spending"
    params = chamadas[0].args_as_dict()["params"]
    assert params["category"] == "Transporte"
    assert params["start_date"] == str(_INICIO_JULHO)
    assert params["end_date"] == str(_FIM_JULHO)

    retorno = _tool_returns(mensagens)[0].content
    assert retorno.total == Decimal("80.00")
    assert retorno.count == 1


@pytest.mark.asyncio
async def test_quais_meus_maiores_gastos_decide_get_top_expenses() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_top_expenses",
                        args={
                            "params": {
                                "start_date": str(_INICIO_MES),
                                "end_date": str(_FIM_MES),
                                "limit": 5,
                            }
                        },
                    )
                ]
            )
        return _resposta_final("Seu maior gasto foi R$ 900,00 no aluguel.")

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, _, _ = _novo_registry()
    deps = _deps(registry, uuid.uuid4())
    ctx = _ctx(deps.user_id)
    for valor, descricao in [("900,00", "Aluguel"), ("50,00", "Mercado")]:
        await registry.create_transaction(
            ctx,
            CreateTransactionParams(
                type=TransactionType.EXPENSE, amount=valor, description=descricao, date=_HOJE
            ),
        )

    with capture_run_messages() as mensagens:
        await agent.run("quais meus maiores gastos?", deps=deps)

    chamadas = _tool_calls(mensagens)
    assert len(chamadas) == 1
    assert chamadas[0].tool_name == "get_top_expenses"

    retorno = _tool_returns(mensagens)[0].content
    assert [item.amount for item in retorno] == [Decimal("900.00"), Decimal("50.00")]


@pytest.mark.asyncio
async def test_pergunta_fora_de_escopo_nao_chama_tool_nenhuma() -> None:
    def roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return _resposta_final("Isso foge do meu escopo — posso ajudar com finanças e agenda!")

    agent = create_agent(model=FunctionModel(roteiro))
    register_tools(agent)
    registry, transacoes, _ = _novo_registry()
    deps = _deps(registry, uuid.uuid4())

    with capture_run_messages() as mensagens:
        result = await agent.run("qual a capital da França?", deps=deps)

    assert _tool_calls(mensagens) == []
    assert "frança" not in result.output.lower()
    assert "paris" not in result.output.lower()
    assert await transacoes.list_by_user(deps.user_id) == []


@pytest.mark.asyncio
async def test_allow_model_requests_false_impede_chamada_real_a_llm() -> None:
    import pydantic_ai.models

    assert pydantic_ai.models.ALLOW_MODEL_REQUESTS is False

    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:pass@localhost/db",
        llm_provider="google",
        llm_model="gemini-2.5-flash",
        google_api_key="fake-key-de-teste",
    )
    modelo_real = build_llm_model(settings)
    agent = create_agent(model=modelo_real)
    register_tools(agent)
    registry, _, _ = _novo_registry()

    with pytest.raises(RuntimeError, match="ALLOW_MODEL_REQUESTS"):
        await agent.run("oi", deps=_deps(registry, uuid.uuid4()))
