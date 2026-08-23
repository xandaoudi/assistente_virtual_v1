"""Suite de avaliação com Gemini real (T3.13, RNF-38) — `uv run python -m app.agent_eval`.

Fora do portão de merge de propósito: chama a LLM de verdade, custa dinheiro, e o resultado
não é determinístico. Mede o que nenhum teste do CI consegue medir — se o Gemini entende as
frases do `EVAL_CASES` em português — e imprime acurácia por categoria mais o custo total,
para que "melhorei o prompt" vire um número em vez de opinião.

Cada caso roda numa sessão isolada, com o usuário já com as categorias padrão (RF-45) — o
mesmo estado que um usuário de verdade teria depois do onboarding (T3.8), não um banco vazio
que penaliza o modelo por não adivinhar uma categoria que ainda não existe.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from app.adapters.agent import Deps, create_agent
from app.adapters.eval_cases import EVAL_CASES
from app.adapters.eval_runner import EvalReport, run_eval_suite
from app.adapters.eval_types import CaseResult, EvalCase
from app.adapters.tools import register_tools
from app.core.asyncio_loop import loop_factory
from app.domain.default_categories import build_default_categories
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TIMEZONE_PADRAO = "America/Sao_Paulo"


async def _nova_sessao() -> tuple[Deps, InMemoryTransactionRepository]:
    transacoes = InMemoryTransactionRepository()
    categorias = InMemoryCategoryRepository()
    registry = ToolRegistry(
        transacoes, categorias, InMemoryUserRepository(), InMemoryToolAuditLogRepository()
    )
    user_id = uuid.uuid4()
    for categoria in build_default_categories(user_id):
        await categorias.add(user_id, categoria)

    deps = Deps(
        user_id=user_id,
        timezone=_TIMEZONE_PADRAO,
        currency="BRL",
        today=datetime.now(ZoneInfo(_TIMEZONE_PADRAO)).date(),
        tools=registry,
    )
    return deps, transacoes


def _linha_reprovado(resultado: CaseResult, casos_por_id: dict[str, EvalCase]) -> str:
    caso = casos_por_id[resultado.case_id]
    detalhe = f" [erro: {resultado.error}]" if resultado.error else ""
    return f"  - {resultado.case_id}: {caso.text!r} -> esperado: {caso.expectation}{detalhe}"


def _formata_relatorio(relatorio: EvalReport) -> str:
    total_casos = len(relatorio.results)
    total_aprovados = sum(1 for r in relatorio.results if r.passed)
    acuracia_geral = total_aprovados / total_casos if total_casos else 0.0

    linhas = ["", "=== Suite de avaliação do agente (T3.13, RNF-38) ===", ""]
    for categoria in sorted(relatorio.summary):
        resumo = relatorio.summary[categoria]
        linhas.append(
            f"{categoria:20s} {resumo.passed:2d}/{resumo.total:2d}  ({resumo.accuracy:.0%})"
        )

    linhas.append("")
    linhas.append(f"Geral: {total_aprovados}/{total_casos} ({acuracia_geral:.0%})")
    linhas.append(f"Custo total (USD): {relatorio.total_cost_usd}")

    reprovados = [r for r in relatorio.results if not r.passed]
    if reprovados:
        casos_por_id = {caso.id: caso for caso in EVAL_CASES}
        linhas.append("")
        linhas.append("Casos reprovados:")
        linhas.extend(_linha_reprovado(resultado, casos_por_id) for resultado in reprovados)

    return "\n".join(linhas)


async def _main() -> None:
    logging.basicConfig(level=logging.WARNING)

    agent = (
        create_agent()
    )  # lê GOOGLE_API_KEY etc. via get_settings() (T3.1) — falha cedo se faltar
    register_tools(agent)

    relatorio = await run_eval_suite(agent, EVAL_CASES, new_session=_nova_sessao)

    print(_formata_relatorio(relatorio))


def main() -> None:
    asyncio.run(_main(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
