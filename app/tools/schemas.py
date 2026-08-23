"""Schemas Pydantic dos parâmetros das tools (RF-85, RNF-05).

Todo schema de parâmetro de tool herda de `ToolParams`, que fixa `extra="forbid"`:
parâmetro desconhecido é erro, não é ignorado silenciosamente. Nenhum schema aqui pode ter
um campo `user_id` — essa identidade vem exclusivamente do `ToolContext` do lado do
servidor (RNF-04, CA-13); a LLM nunca a vê e não pode informá-la.

Os schemas concretos das tools de escrita e de consulta entram nas próximas tarefas
(T2.3, T2.4).
"""

import uuid
from datetime import date as date_type
from decimal import Decimal
from enum import StrEnum
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import TransactionType
from app.domain.money import parse_amount

_LIMITE_MAXIMO_ITENS = 100
_LIMITE_MAXIMO_MESES = 36


class ToolParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaymentMethod(StrEnum):
    """Conjunto fechado do RF-40 — não existe "outro" método de pagamento no catálogo."""

    CASH = "cash"
    DEBIT_CARD = "debit_card"
    CREDIT_CARD = "credit_card"
    PIX = "pix"


class CreateTransactionParams(ToolParams):
    """Parâmetros de `create_transaction` (RF-30, RF-33, §5.2)."""

    type: TransactionType = Field(description="Tipo da transação.")
    amount: str = Field(description='Valor em texto, formato brasileiro (ex.: "45,90").')
    description: str = Field(min_length=1, description="Descrição curta da transação.")
    date: date_type | None = Field(default=None, description="Data da transação. Vazio usa hoje.")
    category: str | None = Field(default=None, description="Nome da categoria, se conhecida.")
    payment_method: PaymentMethod | None = Field(default=None, description="Método de pagamento.")

    @field_validator("amount")
    @classmethod
    def _valida_valor(cls, v: str) -> str:
        # Só valida — o Decimal em si é recalculado em T2.5, que também trata ambiguidade.
        parse_amount(v)
        return v


class UpdateTransactionParams(ToolParams):
    """Parâmetros de `update_transaction` — todo campo além do id é opcional (edição parcial)."""

    transaction_id: uuid.UUID = Field(description="Id da transação a editar.")
    amount: str | None = Field(default=None, description="Novo valor, formato brasileiro.")
    date: date_type | None = Field(default=None, description="Nova data da transação.")
    category: str | None = Field(default=None, description="Novo nome de categoria.")
    description: str | None = Field(default=None, description="Nova descrição.")

    @field_validator("amount")
    @classmethod
    def _valida_valor_opcional(cls, v: str | None) -> str | None:
        if v is not None:
            parse_amount(v)
        return v


class DeleteTransactionParams(ToolParams):
    """Parâmetros de `delete_transaction`."""

    transaction_id: uuid.UUID = Field(description="Id da transação a excluir.")


class TransactionView(BaseModel):
    """Formato comum de uma transação devolvida por uma tool de escrita.

    Deliberadamente menor que o modelo ORM: sem `user_id`, `source` nem `deleted_at` —
    detalhe interno que não ajuda o agente e só custaria token à toa.
    """

    transaction_id: uuid.UUID
    type: TransactionType
    amount: Decimal
    description: str
    date: date_type
    category: str | None = None
    payment_method: PaymentMethod | None = None


class CreateTransactionResult(TransactionView):
    """`category_confidence` é `None` quando a categoria veio explícita do usuário."""

    category_confidence: float | None = None


class UpdateTransactionResult(TransactionView):
    pass


class DeleteTransactionResult(BaseModel):
    transaction_id: uuid.UUID
    deleted: bool


class DateRangeParams(ToolParams):
    """Base para toda tool de consulta que recebe um período (§5.3).

    Reaproveitada por 5 dos 7 schemas de consulta — a mesma validação de intervalo
    (`end_date` não pode ser anterior a `start_date`) vale para todas.
    """

    start_date: date_type = Field(description="Início do período (inclusive).")
    end_date: date_type = Field(description="Fim do período (inclusive).")

    @model_validator(mode="after")
    def _valida_intervalo(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date não pode ser anterior a start_date")
        return self


class GetSummaryParams(DateRangeParams):
    """Parâmetros de `get_summary` (RF-50 a RF-52)."""


class GetSummaryResult(BaseModel):
    total_expenses: Decimal
    total_income: Decimal
    balance: Decimal
    transaction_count: int


class GetSpendingByCategoryParams(DateRangeParams):
    """Parâmetros de `get_spending_by_category` (RF-53)."""

    type: TransactionType | None = Field(default=None, description="Filtra por tipo.")


class CategorySpendingItem(BaseModel):
    category: str
    total: Decimal
    percent: float
    count: int


class GetCategorySpendingParams(DateRangeParams):
    """Parâmetros de `get_category_spending` (RF-54)."""

    category: str = Field(description="Nome da categoria.")


class GetCategorySpendingResult(BaseModel):
    total: Decimal
    count: int
    average: Decimal


class ListTransactionsParams(DateRangeParams):
    """Parâmetros de `list_transactions` (RF-56)."""

    category: str | None = Field(default=None, description="Filtra por nome de categoria.")
    type: TransactionType | None = Field(default=None, description="Filtra por tipo.")
    min_amount: Decimal | None = Field(default=None, ge=0, description="Valor mínimo.")
    max_amount: Decimal | None = Field(default=None, ge=0, description="Valor máximo.")
    query: str | None = Field(default=None, description="Busca por texto na descrição.")
    limit: int | None = Field(
        default=None, ge=1, le=_LIMITE_MAXIMO_ITENS, description="Máximo de itens a devolver."
    )


class ListTransactionsResult(BaseModel):
    """`truncated=True` quando existem mais resultados do que os devolvidos."""

    items: list[TransactionView]
    truncated: bool = False


class ComparePeriodsParams(ToolParams):
    """Parâmetros de `compare_periods` (RF-55)."""

    period_a_start: date_type = Field(description="Início do primeiro período.")
    period_a_end: date_type = Field(description="Fim do primeiro período.")
    period_b_start: date_type = Field(description="Início do segundo período.")
    period_b_end: date_type = Field(description="Fim do segundo período.")
    group_by: str | None = Field(default=None, description="Agrupar a comparação (ex.: categoria).")

    @model_validator(mode="after")
    def _valida_intervalos(self) -> Self:
        if self.period_a_end < self.period_a_start:
            raise ValueError("period_a_end não pode ser anterior a period_a_start")
        if self.period_b_end < self.period_b_start:
            raise ValueError("period_b_end não pode ser anterior a period_b_start")
        return self


class ComparePeriodsResult(BaseModel):
    period_a_total: Decimal
    period_b_total: Decimal
    absolute_change: Decimal
    percent_change: float | None


class GetTopExpensesParams(DateRangeParams):
    """Parâmetros de `get_top_expenses` (RF-57). `limit` é obrigatório — sem teto implícito."""

    limit: int = Field(ge=1, le=_LIMITE_MAXIMO_ITENS, description="Quantidade de despesas.")


class GetMonthlyTrendParams(ToolParams):
    """Parâmetros de `get_monthly_trend` (RF-58)."""

    months: int = Field(ge=1, le=_LIMITE_MAXIMO_MESES, description="Quantos meses incluir.")


class MonthlyTotalItem(BaseModel):
    year: int
    month: int
    total: Decimal


class ListCategoriesParams(ToolParams):
    """Parâmetros de `list_categories` (RF-46)."""

    type: TransactionType | None = Field(default=None, description="Filtra por tipo.")


class CategoryView(BaseModel):
    """Sem `category_id`: o agente referencia categorias pelo nome (ver T2.5)."""

    name: str
    type: TransactionType


class CreateCategoryParams(ToolParams):
    """Parâmetros de `create_category` (RF-46)."""

    name: str = Field(min_length=1, description="Nome da nova categoria.")
    type: TransactionType = Field(description="Tipo da categoria.")


class CreateCategoryResult(BaseModel):
    name: str
    type: TransactionType


class GetUserPreferencesParams(ToolParams):
    """Parâmetros de `get_user_preferences` — nenhum, per §5.4."""


class UpdateUserPreferencesParams(ToolParams):
    """Parâmetros de `update_user_preferences` — todo campo é opcional (edição parcial)."""

    timezone: str | None = Field(default=None, description="Novo fuso horário (nome IANA).")
    currency: str | None = Field(
        default=None, pattern=r"^[A-Z]{3}$", description="Nova moeda padrão (ISO 4217)."
    )
    locale: str | None = Field(default=None, description="Novo idioma/localidade.")

    @field_validator("timezone")
    @classmethod
    def _valida_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"timezone desconhecido: {v!r}") from exc
        return v


class UserPreferencesResult(BaseModel):
    timezone: str
    currency: str
    locale: str


class ResolveRelativeDateParams(ToolParams):
    """Parâmetros de `resolve_relative_date` (§5.4) — tira aritmética de data da LLM."""

    expression: str = Field(description='Expressão de período, ex.: "mês passado".')
    reference_date: date_type | None = Field(
        default=None, description="Data de referência. Vazio usa hoje."
    )


class ResolveRelativeDateResult(BaseModel):
    start_date: date_type
    end_date: date_type
