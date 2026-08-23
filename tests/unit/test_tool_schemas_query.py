import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import TransactionType
from app.tools.schemas import (
    ComparePeriodsParams,
    GetCategorySpendingParams,
    GetMonthlyTrendParams,
    GetSpendingByCategoryParams,
    GetSummaryParams,
    GetSummaryResult,
    GetTopExpensesParams,
    ListTransactionsParams,
    ListTransactionsResult,
    TransactionView,
)

pytestmark = pytest.mark.unit

_INICIO = date(2026, 8, 1)
_FIM = date(2026, 8, 31)


def test_get_summary_params_aceita_entrada_valida() -> None:
    params = GetSummaryParams(start_date=_INICIO, end_date=_FIM)

    assert params.start_date == _INICIO
    assert params.end_date == _FIM


def test_get_summary_params_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        GetSummaryParams(start_date=_INICIO, end_date=_FIM, user_id=str(uuid.uuid4()))


def test_get_summary_params_rejeita_campo_obrigatorio_ausente() -> None:
    with pytest.raises(ValidationError, match="end_date"):
        GetSummaryParams(start_date=_INICIO)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "schema_cls",
    [GetSummaryParams, GetSpendingByCategoryParams],
)
def test_end_date_anterior_a_start_date_e_rejeitado(schema_cls: type) -> None:
    with pytest.raises(ValidationError, match="end_date"):
        schema_cls(start_date=_FIM, end_date=_INICIO)


def test_get_category_spending_params_rejeita_end_date_anterior() -> None:
    with pytest.raises(ValidationError, match="end_date"):
        GetCategorySpendingParams(category="Mercado", start_date=_FIM, end_date=_INICIO)


def test_list_transactions_params_rejeita_end_date_anterior() -> None:
    with pytest.raises(ValidationError, match="end_date"):
        ListTransactionsParams(start_date=_FIM, end_date=_INICIO)


def test_get_top_expenses_params_rejeita_end_date_anterior() -> None:
    with pytest.raises(ValidationError, match="end_date"):
        GetTopExpensesParams(start_date=_FIM, end_date=_INICIO, limit=5)


def test_compare_periods_params_rejeita_periodo_a_invertido() -> None:
    with pytest.raises(ValidationError, match="period_a_end"):
        ComparePeriodsParams(
            period_a_start=_FIM,
            period_a_end=_INICIO,
            period_b_start=_INICIO,
            period_b_end=_FIM,
        )


def test_compare_periods_params_rejeita_periodo_b_invertido() -> None:
    with pytest.raises(ValidationError, match="period_b_end"):
        ComparePeriodsParams(
            period_a_start=_INICIO,
            period_a_end=_FIM,
            period_b_start=_FIM,
            period_b_end=_INICIO,
        )


def test_compare_periods_params_aceita_entrada_valida() -> None:
    params = ComparePeriodsParams(
        period_a_start=_INICIO,
        period_a_end=_FIM,
        period_b_start=date(2026, 7, 1),
        period_b_end=date(2026, 7, 31),
    )
    assert params.group_by is None


def test_get_spending_by_category_params_rejeita_type_fora_do_dominio() -> None:
    with pytest.raises(ValidationError):
        GetSpendingByCategoryParams(start_date=_INICIO, end_date=_FIM, type="transferencia")


def test_list_transactions_params_limit_dentro_da_faixa_e_aceito() -> None:
    params = ListTransactionsParams(start_date=_INICIO, end_date=_FIM, limit=50)
    assert params.limit == 50


def test_list_transactions_params_limit_acima_do_teto_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        ListTransactionsParams(start_date=_INICIO, end_date=_FIM, limit=100_000)


def test_list_transactions_params_limit_zero_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        ListTransactionsParams(start_date=_INICIO, end_date=_FIM, limit=0)


def test_get_top_expenses_params_limit_e_obrigatorio() -> None:
    with pytest.raises(ValidationError, match="limit"):
        GetTopExpensesParams(start_date=_INICIO, end_date=_FIM)  # type: ignore[call-arg]


def test_get_top_expenses_params_limit_acima_do_teto_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        GetTopExpensesParams(start_date=_INICIO, end_date=_FIM, limit=100_000)


def test_get_monthly_trend_params_aceita_entrada_valida() -> None:
    params = GetMonthlyTrendParams(months=6)
    assert params.months == 6


def test_get_monthly_trend_params_rejeita_acima_do_teto() -> None:
    with pytest.raises(ValidationError):
        GetMonthlyTrendParams(months=1000)


def test_get_monthly_trend_params_rejeita_zero() -> None:
    with pytest.raises(ValidationError):
        GetMonthlyTrendParams(months=0)


def test_schema_de_saida_nao_expoe_campo_de_controle_interno() -> None:
    campos = set(TransactionView.model_fields)
    assert "user_id" not in campos
    assert "source" not in campos
    assert "deleted_at" not in campos


def test_get_summary_result_serializa_valores_monetarios_como_string_decimal() -> None:
    resultado = GetSummaryResult(
        total_expenses=Decimal("1234567.89"),
        total_income=Decimal("500.00"),
        balance=Decimal("-1234067.89"),
        transaction_count=3,
    )

    bruto = json.loads(resultado.model_dump_json())
    assert bruto["total_expenses"] == "1234567.89"
    assert bruto["total_income"] == "500.00"
    assert bruto["balance"] == "-1234067.89"


def test_list_transactions_result_serializa_amount_como_string_decimal() -> None:
    resultado = ListTransactionsResult(
        items=[
            TransactionView(
                transaction_id=uuid.uuid4(),
                type=TransactionType.EXPENSE,
                amount=Decimal("45.90"),
                description="Almoço",
                date=_INICIO,
            )
        ],
        truncated=True,
    )

    bruto = json.loads(resultado.model_dump_json())
    assert bruto["items"][0]["amount"] == "45.90"
    assert bruto["truncated"] is True
