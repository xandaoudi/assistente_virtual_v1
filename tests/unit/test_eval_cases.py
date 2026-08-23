"""T3.13 — forma do conjunto de avaliação (RNF-38): no mínimo 30 frases reais em português,
cobrindo as seis categorias exigidas pela tarefa. Isto é uma prova estrutural do dataset —
não roda nenhum caso contra o Gemini (isso é `app/agent_eval.py`, fora do portão de merge)."""

import pytest

from app.adapters.eval_cases import CATEGORIAS_OBRIGATORIAS, EVAL_CASES

pytestmark = pytest.mark.unit


def test_conjunto_tem_pelo_menos_30_casos() -> None:
    assert len(EVAL_CASES) >= 30


def test_todas_as_categorias_obrigatorias_estao_presentes() -> None:
    categorias_presentes = {caso.category for caso in EVAL_CASES}
    faltando = CATEGORIAS_OBRIGATORIAS - categorias_presentes
    assert faltando == set(), f"categorias exigidas pela T3.13 sem nenhum caso: {faltando}"


def test_cada_categoria_obrigatoria_tem_pelo_menos_tres_casos() -> None:
    contagem: dict[str, int] = {}
    for caso in EVAL_CASES:
        contagem[caso.category] = contagem.get(caso.category, 0) + 1

    fracas = {
        categoria: contagem.get(categoria, 0)
        for categoria in CATEGORIAS_OBRIGATORIAS
        if contagem.get(categoria, 0) < 3
    }
    assert fracas == {}, f"categorias com menos de 3 casos: {fracas}"


def test_ids_dos_casos_sao_unicos() -> None:
    ids = [caso.id for caso in EVAL_CASES]
    assert len(ids) == len(set(ids))


def test_nenhuma_frase_de_caso_esta_vazia() -> None:
    assert all(caso.text.strip() for caso in EVAL_CASES)


def test_nenhuma_expectation_esta_vazia() -> None:
    # `expectation` é o que aparece no relatório humano — sem ela, uma reprovação não diz nada.
    assert all(caso.expectation.strip() for caso in EVAL_CASES)
