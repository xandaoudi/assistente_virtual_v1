from datetime import date

import pytest
from pydantic import ValidationError

from app.tools.schemas import ResolveRelativeDateParams, ResolveRelativeDateResult

pytestmark = pytest.mark.unit


def test_resolve_relative_date_params_aceita_so_expression() -> None:
    params = ResolveRelativeDateParams(expression="mês passado")
    assert params.expression == "mês passado"
    assert params.reference_date is None


def test_resolve_relative_date_params_aceita_reference_date() -> None:
    params = ResolveRelativeDateParams(expression="hoje", reference_date=date(2026, 3, 31))
    assert params.reference_date == date(2026, 3, 31)


def test_resolve_relative_date_params_rejeita_campo_obrigatorio_ausente() -> None:
    with pytest.raises(ValidationError, match="expression"):
        ResolveRelativeDateParams()  # type: ignore[call-arg]


def test_resolve_relative_date_params_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        ResolveRelativeDateParams(expression="hoje", user_id="qualquer")  # type: ignore[call-arg]


def test_resolve_relative_date_result_formato() -> None:
    resultado = ResolveRelativeDateResult(start_date=date(2026, 7, 1), end_date=date(2026, 7, 31))
    assert resultado.start_date == date(2026, 7, 1)
    assert resultado.end_date == date(2026, 7, 31)
