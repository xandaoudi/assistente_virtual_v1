from datetime import date

import pytest

from app.domain.errors import DomainError
from app.domain.periods import resolve_period

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 19)  # quarta-feira, data de referência da tabela do T1.2

_CASOS = [
    ("hoje", date(2026, 8, 19), date(2026, 8, 19)),
    ("ontem", date(2026, 8, 18), date(2026, 8, 18)),
    ("esta semana", date(2026, 8, 17), date(2026, 8, 19)),
    ("semana passada", date(2026, 8, 10), date(2026, 8, 16)),
    ("este mês", date(2026, 8, 1), date(2026, 8, 19)),
    ("mês passado", date(2026, 7, 1), date(2026, 7, 31)),
    ("últimos 30 dias", date(2026, 7, 21), date(2026, 8, 19)),
    ("este ano", date(2026, 1, 1), date(2026, 8, 19)),
    ("em julho", date(2026, 7, 1), date(2026, 7, 31)),
    ("no ano passado", date(2025, 1, 1), date(2025, 12, 31)),
]


@pytest.mark.parametrize(("expr", "inicio_esperado", "fim_esperado"), _CASOS)
def test_resolve_period_tabela(expr: str, inicio_esperado: date, fim_esperado: date) -> None:
    inicio, fim = resolve_period(expr, _HOJE)
    assert (inicio, fim) == (inicio_esperado, fim_esperado)


def test_esta_semana_numa_segunda_devolve_um_unico_dia() -> None:
    segunda = date(2026, 8, 17)
    assert resolve_period("esta semana", segunda) == (segunda, segunda)


def test_esta_semana_num_domingo_devolve_os_7_dias() -> None:
    domingo = date(2026, 8, 23)
    inicio, fim = resolve_period("esta semana", domingo)
    assert (inicio, fim) == (date(2026, 8, 17), domingo)
    assert (fim - inicio).days == 6


def test_este_mes_no_dia_1_devolve_um_unico_dia() -> None:
    dia_1 = date(2026, 8, 1)
    assert resolve_period("este mês", dia_1) == (dia_1, dia_1)


def test_mes_passado_a_partir_de_31_03_2026() -> None:
    inicio, fim = resolve_period("mês passado", date(2026, 3, 31))
    assert (inicio, fim) == (date(2026, 2, 1), date(2026, 2, 28))


def test_mes_passado_a_partir_de_15_01_2026_vira_o_ano() -> None:
    inicio, fim = resolve_period("mês passado", date(2026, 1, 15))
    assert (inicio, fim) == (date(2025, 12, 1), date(2025, 12, 31))


def test_expressao_desconhecida_levanta_domain_error_com_mensagem_util() -> None:
    with pytest.raises(DomainError, match="depois de amanhã"):
        resolve_period("depois de amanhã", _HOJE)


def test_mes_nomeado_desconhecido_levanta_domain_error() -> None:
    with pytest.raises(DomainError):
        resolve_period("em fevereireiro", _HOJE)


def test_mes_nomeado_com_ano_explicito_nao_ignora_o_ano() -> None:
    inicio, fim = resolve_period("em março de 2024", _HOJE)
    assert (inicio, fim) == (date(2024, 3, 1), date(2024, 3, 31))


def test_mes_nomeado_com_ano_invalido_levanta_domain_error() -> None:
    with pytest.raises(DomainError):
        resolve_period("em março de abc", _HOJE)
