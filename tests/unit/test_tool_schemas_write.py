import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import TransactionType
from app.tools.schemas import (
    CreateTransactionParams,
    CreateTransactionResult,
    DeleteTransactionParams,
    PaymentMethod,
    UpdateTransactionParams,
)

pytestmark = pytest.mark.unit

_CAMPOS_MINIMOS = {"type": "expense", "amount": "10", "description": "Café"}


def test_create_transaction_params_aceita_entrada_valida() -> None:
    params = CreateTransactionParams(
        type=TransactionType.EXPENSE,
        amount="45,90",
        description="Almoço",
        date=date(2026, 8, 20),
        category="Alimentação",
        payment_method=PaymentMethod.PIX,
    )

    assert params.type == TransactionType.EXPENSE
    assert params.amount == "45,90"
    assert params.date == date(2026, 8, 20)
    assert params.category == "Alimentação"
    assert params.payment_method == PaymentMethod.PIX


def test_create_transaction_params_aceita_so_os_campos_obrigatorios() -> None:
    params = CreateTransactionParams(**_CAMPOS_MINIMOS)

    assert params.date is None
    assert params.category is None
    assert params.payment_method is None


@pytest.mark.parametrize("campo_ausente", ["type", "amount", "description"])
def test_create_transaction_params_rejeita_campo_obrigatorio_ausente(
    campo_ausente: str,
) -> None:
    dados = {**_CAMPOS_MINIMOS}
    del dados[campo_ausente]

    with pytest.raises(ValidationError, match=campo_ausente):
        CreateTransactionParams(**dados)


def test_create_transaction_params_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        CreateTransactionParams(**_CAMPOS_MINIMOS, user_id=str(uuid.uuid4()))


def test_create_transaction_params_rejeita_enum_fora_do_dominio() -> None:
    with pytest.raises(ValidationError):
        CreateTransactionParams(**{**_CAMPOS_MINIMOS, "type": "transferencia"})


def test_create_transaction_params_rejeita_payment_method_fora_do_dominio() -> None:
    with pytest.raises(ValidationError):
        CreateTransactionParams(**_CAMPOS_MINIMOS, payment_method="boleto")


def test_create_transaction_params_rejeita_valor_negativo_antes_do_dominio() -> None:
    with pytest.raises(ValidationError):
        CreateTransactionParams(**{**_CAMPOS_MINIMOS, "amount": "-10,00"})


def test_create_transaction_params_rejeita_data_em_formato_invalido() -> None:
    with pytest.raises(ValidationError):
        CreateTransactionParams(**_CAMPOS_MINIMOS, date="32/13/2026")


def test_update_transaction_params_aceita_edicao_parcial() -> None:
    params = UpdateTransactionParams(transaction_id=uuid.uuid4(), description="Nova descrição")

    assert params.amount is None
    assert params.date is None
    assert params.category is None


def test_update_transaction_params_rejeita_sem_transaction_id() -> None:
    with pytest.raises(ValidationError, match="transaction_id"):
        UpdateTransactionParams(description="Nova descrição")  # type: ignore[call-arg]


def test_update_transaction_params_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        UpdateTransactionParams(transaction_id=uuid.uuid4(), user_id=str(uuid.uuid4()))


def test_update_transaction_params_rejeita_valor_negativo() -> None:
    with pytest.raises(ValidationError):
        UpdateTransactionParams(transaction_id=uuid.uuid4(), amount="-1")


def test_update_transaction_params_rejeita_data_em_formato_invalido() -> None:
    with pytest.raises(ValidationError):
        UpdateTransactionParams(transaction_id=uuid.uuid4(), date="ontem")


def test_delete_transaction_params_aceita_entrada_valida() -> None:
    transaction_id = uuid.uuid4()
    params = DeleteTransactionParams(transaction_id=transaction_id)

    assert params.transaction_id == transaction_id


def test_delete_transaction_params_rejeita_sem_transaction_id() -> None:
    with pytest.raises(ValidationError):
        DeleteTransactionParams()  # type: ignore[call-arg]


def test_delete_transaction_params_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        DeleteTransactionParams(transaction_id=uuid.uuid4(), user_id=str(uuid.uuid4()))


def test_create_transaction_result_serializa_valor_como_string_decimal() -> None:
    resultado = CreateTransactionResult(
        transaction_id=uuid.uuid4(),
        type=TransactionType.EXPENSE,
        amount=Decimal("1234567.89"),
        description="Aluguel",
        date=date(2026, 8, 1),
    )

    bruto = json.loads(resultado.model_dump_json())
    assert bruto["amount"] == "1234567.89"


def test_create_transaction_result_category_confidence_e_opcional() -> None:
    resultado = CreateTransactionResult(
        transaction_id=uuid.uuid4(),
        type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        description="Café",
        date=date(2026, 8, 1),
    )

    assert resultado.category_confidence is None
