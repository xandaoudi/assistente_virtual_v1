from datetime import date

import pytest

from app.domain.enums import TransactionType
from app.tools.audit import redact_params
from app.tools.schemas import CreateTransactionParams, ListTransactionsParams

pytestmark = pytest.mark.unit


def test_redact_params_oculta_amount_e_description() -> None:
    params = CreateTransactionParams(
        type=TransactionType.EXPENSE,
        amount="1.234,56",
        description="almoço com cliente",
        date=date(2026, 8, 20),
        category="Alimentação",
    )

    redigido = redact_params(params)

    assert redigido["amount"] == "[REDACTED]"
    assert redigido["description"] == "[REDACTED]"
    assert "1.234,56" not in str(redigido)
    assert "almoço com cliente" not in str(redigido)


def test_redact_params_preserva_campos_nao_sensiveis() -> None:
    params = CreateTransactionParams(
        type=TransactionType.EXPENSE,
        amount="10,00",
        description="qualquer coisa",
        date=date(2026, 8, 20),
        category="Alimentação",
    )

    redigido = redact_params(params)

    assert redigido["type"] == "expense"
    assert redigido["date"] == "2026-08-20"
    assert redigido["category"] == "Alimentação"


def test_redact_params_oculta_query_e_faixa_de_valor() -> None:
    params = ListTransactionsParams(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        query="presente de aniversário",
        min_amount=10,
        max_amount=100,
    )

    redigido = redact_params(params)

    assert redigido["query"] == "[REDACTED]"
    assert redigido["min_amount"] == "[REDACTED]"
    assert redigido["max_amount"] == "[REDACTED]"
    assert "presente de aniversário" not in str(redigido)
