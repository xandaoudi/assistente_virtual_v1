"""Resolução de expressões de período em datas absolutas (RF-59, RN-09, RN-10)."""

from collections.abc import Callable
from datetime import date, timedelta

from app.domain.errors import DomainError

_MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def _hoje(today: date) -> tuple[date, date]:
    return today, today


def _ontem(today: date) -> tuple[date, date]:
    ontem = today - timedelta(days=1)
    return ontem, ontem


def _esta_semana(today: date) -> tuple[date, date]:
    inicio = today - timedelta(days=today.weekday())
    return inicio, today


def _semana_passada(today: date) -> tuple[date, date]:
    inicio_atual = today - timedelta(days=today.weekday())
    return inicio_atual - timedelta(days=7), inicio_atual - timedelta(days=1)


def _este_mes(today: date) -> tuple[date, date]:
    return today.replace(day=1), today


def _mes_passado(today: date) -> tuple[date, date]:
    # `date.replace(month=...)` estoura em dias que não existem no mês anterior
    # (ex.: 31/03 -> fevereiro). Ir ao dia 1º do mês atual e subtrair um dia
    # sempre cai no último dia do mês anterior, sem casos especiais.
    fim = today.replace(day=1) - timedelta(days=1)
    return fim.replace(day=1), fim


def _ultimos_30_dias(today: date) -> tuple[date, date]:
    return today - timedelta(days=29), today


def _este_ano(today: date) -> tuple[date, date]:
    return date(today.year, 1, 1), today


def _ano_passado(today: date) -> tuple[date, date]:
    ano = today.year - 1
    return date(ano, 1, 1), date(ano, 12, 31)


_EXPRESSOES: dict[str, Callable[[date], tuple[date, date]]] = {
    "hoje": _hoje,
    "ontem": _ontem,
    "esta semana": _esta_semana,
    "semana passada": _semana_passada,
    "este mês": _este_mes,
    "mês passado": _mes_passado,
    "últimos 30 dias": _ultimos_30_dias,
    "este ano": _este_ano,
    "no ano passado": _ano_passado,
}


def _ultimo_dia_do_mes(ano: int, mes: int) -> int:
    proximo_mes_dia_1 = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return (proximo_mes_dia_1 - timedelta(days=1)).day


def _mes_nomeado(nome: str, ano: int) -> tuple[date, date]:
    mes = _MESES.get(nome)
    if mes is None:
        raise DomainError(f"Mês desconhecido: {nome!r}")
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, _ultimo_dia_do_mes(ano, mes))
    return inicio, fim


def resolve_period(expr: str, today: date) -> tuple[date, date]:
    """Traduz uma expressão de período (ex.: "mês passado") para `(início, fim)`.

    `today` é sempre recebido como parâmetro — nunca `date.today()` internamente — para
    que o resultado seja determinístico e testável sem congelar o relógio.

    Levanta `DomainError` se a expressão não for reconhecida.
    """
    normalizado = expr.strip().lower()

    handler = _EXPRESSOES.get(normalizado)
    if handler is not None:
        return handler(today)

    if normalizado.startswith("em "):
        nome_mes, _, ano_str = normalizado.removeprefix("em ").strip().partition(" de ")
        ano_str = ano_str.strip()
        ano = _parse_ano(ano_str) if ano_str else today.year
        return _mes_nomeado(nome_mes.strip(), ano)

    raise DomainError(f"Expressão de período desconhecida: {expr!r}")


def _parse_ano(texto: str) -> int:
    if not texto.isdigit():
        raise DomainError(f"Ano inválido em expressão de período: {texto!r}")
    return int(texto)
