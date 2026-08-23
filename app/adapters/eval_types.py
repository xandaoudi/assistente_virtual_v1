"""Tipos e funções puras da suite de avaliação com modelo real (T3.13, RNF-38).

Nada aqui chama o Gemini nem importa `pydantic_ai` — só o suficiente para descrever um
caso de avaliação, o que foi observado ao rodá-lo, e como isso vira pontuação e relatório.
É a parte da suite que pode (e deve) ser testada como qualquer outra lógica pura do projeto;
`app/adapters/eval_runner.py` é quem de fato executa um caso contra o modelo real.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from app.models.transaction import Transaction


@dataclass(frozen=True)
class EvalObservation:
    """O que aconteceu ao rodar um `EvalCase`: tools chamadas com sucesso, transações que
    passaram a existir para o usuário do caso, e o texto final da resposta."""

    tool_calls: list[str]
    created_transactions: list[Transaction]
    output_text: str


CaseCheck = Callable[[EvalObservation], bool]


@dataclass(frozen=True)
class EvalCase:
    """Um caso do conjunto de avaliação (§ T3.13): frase real em português, categoria, e o
    critério que decide se o agente acertou. `expectation` é só para o relatório humano —
    a decisão de fato é `check`."""

    id: str
    category: str
    text: str
    expectation: str
    check: CaseCheck


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    passed: bool
    error: str | None = None


def score_case(case: EvalCase, observation: EvalObservation) -> CaseResult:
    """Aplica `case.check` à observação. Um `check` que levanta exceção nunca derruba a
    suite inteira — vira reprovação com o motivo anotado, como qualquer outro caso."""
    try:
        passou = case.check(observation)
    except Exception as exc:
        return CaseResult(case_id=case.id, category=case.category, passed=False, error=str(exc))
    return CaseResult(case_id=case.id, category=case.category, passed=passou)


@dataclass(frozen=True)
class CategorySummary:
    total: int
    passed: int

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0


def summarize_results(results: list[CaseResult]) -> dict[str, CategorySummary]:
    """Acurácia por categoria (§ T3.13) — a linha de base que dá sentido a "melhorei o prompt"."""
    por_categoria: dict[str, list[CaseResult]] = {}
    for resultado in results:
        por_categoria.setdefault(resultado.category, []).append(resultado)

    return {
        categoria: CategorySummary(total=len(itens), passed=sum(1 for item in itens if item.passed))
        for categoria, itens in por_categoria.items()
    }


def total_cost(costs: list[Decimal | None]) -> Decimal:
    """Soma os custos conhecidos — `None` (modelo/provider sem tabela de preço) não conta
    como zero, só é ignorado; sem custo nenhum conhecido, o total é `Decimal("0")`."""
    return sum((custo for custo in costs if custo is not None), Decimal("0"))
