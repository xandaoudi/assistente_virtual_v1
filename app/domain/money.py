"""Dinheiro como `Decimal` e parser de valores em formato brasileiro (RF-33)."""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.domain.errors import DomainError

Money = Decimal

_TWO_PLACES = Decimal("0.01")
_THOUSAND_MULTIPLIER = Decimal(1000)

_CURRENCY_SYMBOL_RE = re.compile(r"[Rr]\$")
_TOKEN_RE = re.compile(r"(?P<sign>-)?\s*(?P<num>\d[\d.,]*)(?P<mult>[kK])?")


@dataclass(frozen=True)
class ParsedAmount:
    """Resultado de `parse_amount`.

    `ambiguous` sinaliza quando a heurística de milhar-vs-decimal foi aplicada, para o
    agente pedir confirmação ao usuário (RF-35) em vez de assumir o valor calculado.
    """

    amount: Money
    ambiguous: bool = False


def to_money(value: Decimal) -> Money:
    """Quantiza um `Decimal` para 2 casas, arredondando para cima em caso de empate."""
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _normalize_digits(num: str) -> tuple[str, bool]:
    """Converte o token numérico para um formato aceito por `Decimal`.

    Devolve os dígitos normalizados e se a heurística de milhar-vs-decimal foi aplicada.
    """
    if "," in num:
        integer_part, _, decimal_part = num.rpartition(",")
        return f"{integer_part.replace('.', '')}.{decimal_part}", False

    if "." not in num:
        return num, False

    grupos = num.split(".")
    if len(grupos[-1]) != 3:
        # ponto decimal, estilo inglês (ex.: "45.9", "45.90").
        return num, False

    # "1.250" (sem vírgula) é ambíguo: milhar (padrão BR) ou decimal (padrão EN).
    # Vários grupos de milhar ("1.234.567") não são ambíguos, desde que todos os
    # grupos após o primeiro tenham exatamente 3 dígitos — agrupamento irregular
    # (ex.: "12.3.456") não é um valor reconhecível.
    if len(grupos) > 2 and not all(len(grupo) == 3 for grupo in grupos[1:]):
        raise DomainError(f"Não foi possível reconhecer um valor em {num!r}")

    return "".join(grupos), len(grupos) == 2


def parse_amount(texto: str) -> ParsedAmount:
    """Interpreta um valor monetário em formato brasileiro (ex.: "R$ 1.250,00", "2k").

    Levanta `DomainError` se nenhum número reconhecível estiver presente, ou se o valor
    resultante for negativo (RN-04).
    """
    # Remove o símbolo de moeda antes de procurar o sinal: sem isso, "-R$ 50,00" não
    # reconhece o "-" como sinal porque ele fica longe demais do primeiro dígito.
    texto_sem_moeda = _CURRENCY_SYMBOL_RE.sub("", texto)
    match = _TOKEN_RE.search(texto_sem_moeda)
    if match is None:
        raise DomainError(f"Não foi possível reconhecer um valor em {texto!r}")

    digits, ambiguous = _normalize_digits(match.group("num"))

    try:
        value = Decimal(digits)
    except InvalidOperation as exc:
        raise DomainError(f"Não foi possível reconhecer um valor em {texto!r}") from exc

    if match.group("mult"):
        value *= _THOUSAND_MULTIPLIER
    if match.group("sign"):
        value = -value

    if value < 0:
        raise DomainError("Valor monetário não pode ser negativo")

    return ParsedAmount(amount=to_money(value), ambiguous=ambiguous)
