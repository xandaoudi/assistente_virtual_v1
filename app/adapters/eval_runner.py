"""Execução da suite de avaliação contra um agente real (T3.13, RNF-38).

Único módulo da suite que de fato chama `agent.run()` — por isso é o único que importa
`pydantic_ai` (RF-86). `app/agent_eval.py` é quem monta o agente de produção (Gemini de
verdade) e chama `run_eval_suite`; os testes de fiação usam `FunctionModel` (ver
`tests/e2e/test_eval_runner.py`) para provar esta ligação sem gastar uma chamada real.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.usage import RunUsage

from app.adapters.agent import Deps
from app.adapters.eval_types import (
    CaseResult,
    CategorySummary,
    EvalCase,
    EvalObservation,
    score_case,
    summarize_results,
    total_cost,
)
from app.domain.repositories import TransactionRepository

NewSession = Callable[[], Awaitable[tuple[Deps, TransactionRepository]]]


async def run_case(
    agent: Agent[Deps, str],
    deps: Deps,
    transaction_repository: TransactionRepository,
    case: EvalCase,
) -> tuple[EvalObservation, RunUsage]:
    """Roda `case.text` contra o agente e observa o que ele decidiu: tools concluídas com
    sucesso e as transações que passaram a existir para `deps.user_id`."""
    with capture_run_messages() as mensagens:
        result = await agent.run(case.text, deps=deps)

    tool_calls = [
        part.tool_name
        for message in mensagens
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.outcome == "success"
    ]
    transacoes = await transaction_repository.list_by_user(deps.user_id)
    observation = EvalObservation(
        tool_calls=tool_calls, created_transactions=transacoes, output_text=result.output
    )
    return observation, result.usage


@dataclass(frozen=True)
class EvalReport:
    results: list[CaseResult]
    summary: dict[str, CategorySummary]
    total_cost_usd: Decimal


async def run_eval_suite(
    agent: Agent[Deps, str], cases: list[EvalCase], *, new_session: NewSession
) -> EvalReport:
    """Roda todo `cases` contra `agent`, cada um numa sessão isolada (`new_session`) — um
    caso nunca vê a transação criada por outro."""
    resultados: list[CaseResult] = []
    custos: list[Decimal | None] = []

    for case in cases:
        deps, transaction_repository = await new_session()
        observation, usage = await run_case(agent, deps, transaction_repository, case)
        resultados.append(score_case(case, observation))
        custos.append(usage.cost)

    return EvalReport(
        results=resultados,
        summary=summarize_results(resultados),
        total_cost_usd=total_cost(custos),
    )
