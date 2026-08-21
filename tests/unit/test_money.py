from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.errors import DomainError
from app.domain.money import parse_amount

pytestmark = pytest.mark.unit

_CASES = [
    ("45", "45.00"),
    ("45,90", "45.90"),
    ("R$ 1.250,00", "1250.00"),
    ("1.234.567,89", "1234567.89"),
    ("0,50", "0.50"),
    ("1,2k", "1200.00"),
    ("2k", "2000.00"),
    ("3.5k", "3500.00"),
    ("R$45", "45.00"),
    ("45.9", "45.90"),
]


@pytest.mark.parametrize(("texto", "esperado"), _CASES)
def test_parse_amount_tabela(texto: str, esperado: str) -> None:
    resultado = parse_amount(texto)
    assert resultado.amount == Decimal(esperado)


def test_parse_amount_rejeita_valor_negativo() -> None:
    with pytest.raises(DomainError):
        parse_amount("-45,00")


def test_parse_amount_sem_numero_levanta_domain_error() -> None:
    with pytest.raises(DomainError):
        parse_amount("abacate")


def test_parse_amount_agrupamento_de_milhar_irregular_levanta_domain_error() -> None:
    with pytest.raises(DomainError):
        parse_amount("12.3.456")


def test_parse_amount_1250_marca_ambiguo() -> None:
    resultado = parse_amount("1.250")
    assert resultado.amount == Decimal("1250.00")
    assert resultado.ambiguous is True


def test_parse_amount_1_25_nao_marca_ambiguo() -> None:
    resultado = parse_amount("1.25")
    assert resultado.amount == Decimal("1.25")
    assert resultado.ambiguous is False


def test_soma_de_mil_parcelas_de_um_centavo() -> None:
    total = sum((Decimal("0.01") for _ in range(1000)), start=Decimal("0"))
    assert total == Decimal("10.00")


def test_modulo_nao_usa_float() -> None:
    caminho = Path(__file__).resolve().parents[2] / "app" / "domain" / "money.py"
    fonte = caminho.read_text(encoding="utf-8")
    assert "float" not in fonte
