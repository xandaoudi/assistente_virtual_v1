import pytest

from app.domain.categorizer import suggest_category

pytestmark = pytest.mark.unit

_MAPEAMENTOS_CONHECIDOS = [
    ("Comprei no mercado", "Mercado"),
    ("Fiz compras no supermercado", "Mercado"),
    ("Fui no atacadão", "Mercado"),
    ("Pedi um Uber", "Transporte"),
    ("Chamei um 99", "Transporte"),
    ("Abasteci com gasolina", "Transporte"),
    ("Peguei o ônibus", "Transporte"),
    ("Fui à farmácia", "Saúde"),
    ("Marquei uma consulta", "Saúde"),
    ("Fiz um exame", "Saúde"),
    ("Paguei o aluguel", "Moradia"),
    ("Matriculei no curso", "Educação"),
    ("Fui ao cinema", "Lazer"),
    ("Comprei uma roupa nova", "Vestuário"),
    ("Assinei o Netflix", "Assinaturas"),
    ("Jantei num restaurante", "Alimentação"),
]


@pytest.mark.parametrize(("descricao", "categoria_esperada"), _MAPEAMENTOS_CONHECIDOS)
def test_cada_mapeamento_conhecido_acerta_a_categoria(
    descricao: str, categoria_esperada: str
) -> None:
    resultado = suggest_category(descricao)
    assert resultado.category == categoria_esperada


def test_descricao_desconhecida_devolve_outros_com_confianca_baixa() -> None:
    resultado = suggest_category("xyz totalmente sem relação com nada conhecido")

    assert resultado.category == "Outros"
    assert resultado.confidence < 0.5


def test_insensivel_a_acento_e_maiuscula() -> None:
    resultado = suggest_category("FUI NA FARMÁCIA COMPRAR REMÉDIO")

    assert resultado.category == "Saúde"


def test_descricao_com_multiplas_pistas_escolhe_a_de_maior_peso_de_forma_deterministica() -> None:
    # Duas pistas de Saúde ("consulta", "remedio") contra uma de Transporte ("uber").
    descricao = "fui de uber comprar remedio depois fazer uma consulta"

    resultado = suggest_category(descricao)

    assert resultado.category == "Saúde"


def test_funcao_e_pura_mesma_entrada_mesma_saida() -> None:
    descricao = "Comprei no mercado"

    assert suggest_category(descricao) == suggest_category(descricao)


def test_99_nao_casa_como_substring_de_um_preco() -> None:
    # "99" é a palavra-chave do app de transporte, mas não pode casar dentro de um preço
    # como "R$ 1,99" ou "cinema 199" — regressão do bug de substring.
    resultado = suggest_category("cinema 199")

    assert resultado.category == "Lazer"
