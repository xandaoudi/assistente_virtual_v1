"""Orçamento de tokens do catálogo de tools (§3.3.5, RNF-27).

Cada palavra de uma descrição de tool é paga em toda requisição à LLM. Este módulo
serializa o schema de parâmetros de cada tool (o que de fato vira JSON Schema na
requisição) e aproxima o custo em tokens, para tornar visível — e testável — o que
hoje é invisível: o catálogo engordando sem ninguém perceber.

A aproximação de ~4 caracteres por token é a mesma usada no dimensionamento da T2.12;
serve para orçamento e comparação relativa, não para prever a fatura exata.
"""

import json
import math
from dataclasses import dataclass

from pydantic import BaseModel

from app.tools.schemas import (
    ComparePeriodsParams,
    CreateCategoryParams,
    CreateTransactionParams,
    DeleteTransactionParams,
    GetCategorySpendingParams,
    GetMonthlyTrendParams,
    GetSpendingByCategoryParams,
    GetSummaryParams,
    GetTopExpensesParams,
    GetUserPreferencesParams,
    ListCategoriesParams,
    ListTransactionsParams,
    ResolveRelativeDateParams,
    UpdateTransactionParams,
    UpdateUserPreferencesParams,
)

_CARACTERES_POR_TOKEN = 4

TOOL_PARAMS_SCHEMAS: dict[str, type[BaseModel]] = {
    "create_transaction": CreateTransactionParams,
    "update_transaction": UpdateTransactionParams,
    "delete_transaction": DeleteTransactionParams,
    "get_summary": GetSummaryParams,
    "get_spending_by_category": GetSpendingByCategoryParams,
    "get_category_spending": GetCategorySpendingParams,
    "list_transactions": ListTransactionsParams,
    "compare_periods": ComparePeriodsParams,
    "get_top_expenses": GetTopExpensesParams,
    "get_monthly_trend": GetMonthlyTrendParams,
    "list_categories": ListCategoriesParams,
    "create_category": CreateCategoryParams,
    "get_user_preferences": GetUserPreferencesParams,
    "update_user_preferences": UpdateUserPreferencesParams,
    "resolve_relative_date": ResolveRelativeDateParams,
}


@dataclass(frozen=True)
class TokenReport:
    per_tool: dict[str, int]
    total: int


def estimate_tokens(texto: str) -> int:
    return math.ceil(len(texto) / _CARACTERES_POR_TOKEN)


def schema_token_report() -> TokenReport:
    """Serializa o schema de cada tool e soma uma estimativa de tokens por tool e total."""
    por_tool: dict[str, int] = {}
    for nome, schema_cls in TOOL_PARAMS_SCHEMAS.items():
        schema_json = json.dumps(
            schema_cls.model_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        por_tool[nome] = estimate_tokens(nome) + estimate_tokens(schema_json)
    return TokenReport(per_tool=por_tool, total=sum(por_tool.values()))


def _imprimir_relatorio() -> None:
    relatorio = schema_token_report()
    for nome, tokens in sorted(relatorio.per_tool.items(), key=lambda item: item[1], reverse=True):
        print(f"{nome:30s} {tokens:6d} tokens")
    print("-" * 40)
    print(f"{'TOTAL':30s} {relatorio.total:6d} tokens")


if __name__ == "__main__":
    _imprimir_relatorio()
