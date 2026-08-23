"""T3.13 — peças puras da suite de avaliação (RNF-38): pontuação de um caso, agregação por
categoria e soma de custo. Nenhum teste aqui chama o Gemini — são as únicas partes da
suite determinísticas o bastante para entrar no portão de merge; a suite completa, que roda
contra o modelo real, é executada por comando explícito (`app/agent_eval.py`)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.adapters.eval_types import (
    CaseResult,
    EvalCase,
    EvalObservation,
    score_case,
    summarize_results,
    total_cost,
)
from app.domain.enums import TransactionSource, TransactionType
from app.models.transaction import Transaction

pytestmark = pytest.mark.unit


def _transacao(tipo: TransactionType, amount: str) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type=tipo,
        amount=Decimal(amount),
        currency="BRL",
        date=date(2026, 8, 23),
        source=TransactionSource.CHAT,
    )


def _obs(
    tool_calls: list[str] | None = None,
    transacoes: list[Transaction] | None = None,
    texto: str = "",
) -> EvalObservation:
    return EvalObservation(
        tool_calls=tool_calls or [], created_transactions=transacoes or [], output_text=texto
    )


def _caso(check: object, case_id: str = "caso-1", category: str = "categoria-teste") -> EvalCase:
    return EvalCase(
        id=case_id, category=category, text="frase de teste", expectation="algo", check=check
    )


def test_score_case_aprova_quando_o_check_devolve_verdadeiro() -> None:
    caso = _caso(lambda obs: True)

    resultado = score_case(caso, _obs())

    assert resultado == CaseResult(case_id="caso-1", category="categoria-teste", passed=True)


def test_score_case_reprova_quando_o_check_devolve_falso() -> None:
    caso = _caso(lambda obs: False)

    resultado = score_case(caso, _obs())

    assert resultado.passed is False
    assert resultado.error is None


def test_score_case_reprova_sem_derrubar_a_suite_quando_o_check_levanta_excecao() -> None:
    def check_quebrado(obs: EvalObservation) -> bool:
        raise RuntimeError("bug no critério do caso, não na suite")

    caso = _caso(check_quebrado)

    resultado = score_case(caso, _obs())

    assert resultado.passed is False
    assert resultado.error is not None
    assert "bug no critério" in resultado.error


def test_summarize_results_agrupa_e_calcula_acuracia_por_categoria() -> None:
    resultados = [
        CaseResult(case_id="a1", category="ambiguidade", passed=True),
        CaseResult(case_id="a2", category="ambiguidade", passed=False),
        CaseResult(case_id="v1", category="valores", passed=True),
        CaseResult(case_id="v2", category="valores", passed=True),
    ]

    resumo = summarize_results(resultados)

    assert resumo["ambiguidade"].total == 2
    assert resumo["ambiguidade"].passed == 1
    assert resumo["ambiguidade"].accuracy == pytest.approx(0.5)
    assert resumo["valores"].total == 2
    assert resumo["valores"].passed == 2
    assert resumo["valores"].accuracy == pytest.approx(1.0)


def test_summarize_results_categoria_sem_casos_nao_aparece() -> None:
    resumo = summarize_results([])

    assert resumo == {}


def test_total_cost_soma_ignorando_valores_desconhecidos() -> None:
    custos = [Decimal("0.001"), None, Decimal("0.002"), None]

    assert total_cost(custos) == Decimal("0.003")


def test_total_cost_de_lista_vazia_e_zero() -> None:
    assert total_cost([]) == Decimal("0")
