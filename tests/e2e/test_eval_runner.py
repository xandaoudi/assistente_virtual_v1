"""T3.13 — prova de fiação da suite de avaliação (`app/adapters/eval_runner.py`) com
`FunctionModel`, sem tocar o Gemini de verdade.

A suite real, contra o modelo real, roda por comando explícito (`app/agent_eval.py`) e não
entra no portão de merge (RNF-38) — mas a fiação `agent.run()` -> `EvalObservation` ->
`score_case` -> `EvalReport` é determinística e precisa estar certa antes de gastar uma
chamada real com ela. É isso que este arquivo prova.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent
from app.adapters.eval_runner import run_case, run_eval_suite
from app.adapters.eval_types import EvalCase
from app.adapters.tools import register_tools
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.e2e

_HOJE = date(2026, 8, 23)

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


def _roteiro_cria_transacao(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(parts=[_CALL_CRIA_TRANSACAO])
    return ModelResponse(parts=[TextPart(content="Registrado.")])


async def _nova_sessao() -> tuple[Deps, InMemoryTransactionRepository]:
    transacoes = InMemoryTransactionRepository()
    registry = ToolRegistry(
        transacoes,
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )
    deps = Deps(
        user_id=uuid.uuid4(),
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=_HOJE,
        tools=registry,
    )
    return deps, transacoes


@pytest.mark.asyncio
async def test_run_case_observa_a_tool_chamada_e_a_transacao_persistida() -> None:
    agent = create_agent(model=FunctionModel(_roteiro_cria_transacao))
    register_tools(agent)
    deps, transacoes = await _nova_sessao()
    caso = EvalCase(
        id="c1",
        category="teste",
        text="gastei 45 no mercado",
        expectation="despesa de R$ 45,00",
        check=lambda obs: True,
    )

    observacao, usage = await run_case(agent, deps, transacoes, caso)

    assert observacao.tool_calls == ["create_transaction"]
    assert len(observacao.created_transactions) == 1
    assert observacao.created_transactions[0].amount == Decimal("45.00")
    assert observacao.output_text == "Registrado."
    assert usage.requests >= 1


@pytest.mark.asyncio
async def test_run_case_isola_sessoes_diferentes_uma_da_outra() -> None:
    agent = create_agent(model=FunctionModel(_roteiro_cria_transacao))
    register_tools(agent)
    deps_a, transacoes_a = await _nova_sessao()
    deps_b, transacoes_b = await _nova_sessao()
    caso = EvalCase(
        id="c1", category="teste", text="gastei 45 no mercado", expectation="", check=lambda o: True
    )

    await run_case(agent, deps_a, transacoes_a, caso)

    assert len(await transacoes_a.list_by_user(deps_a.user_id)) == 1
    assert await transacoes_b.list_by_user(deps_b.user_id) == []


@pytest.mark.asyncio
async def test_run_eval_suite_gera_relatorio_com_resultados_resumo_e_custo() -> None:
    agent = create_agent(model=FunctionModel(_roteiro_cria_transacao))
    register_tools(agent)

    casos = [
        EvalCase(
            id="ok",
            category="cat-a",
            text="gastei 45 no mercado",
            expectation="cria uma transação",
            check=lambda obs: len(obs.created_transactions) == 1,
        ),
        EvalCase(
            id="falha",
            category="cat-a",
            text="gastei 45 no mercado",
            expectation="não deveria criar nada (propositalmente errado, prova reprovação)",
            check=lambda obs: len(obs.created_transactions) == 0,
        ),
    ]

    relatorio = await run_eval_suite(agent, casos, new_session=_nova_sessao)

    assert len(relatorio.results) == 2
    aprovados = {r.case_id: r.passed for r in relatorio.results}
    assert aprovados == {"ok": True, "falha": False}

    assert relatorio.summary["cat-a"].total == 2
    assert relatorio.summary["cat-a"].passed == 1
    assert relatorio.summary["cat-a"].accuracy == pytest.approx(0.5)

    # FunctionModel não tem tabela de preço real — custo desconhecido soma zero, não None.
    assert relatorio.total_cost_usd == Decimal("0")
