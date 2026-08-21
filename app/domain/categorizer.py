"""Sugestão determinística de categoria por palavra-chave (RF-34) — baseline pré-LLM.

Existe para medir, na Etapa 3, se a LLM realmente melhora a categorização em relação a um
baseline grátis e instantâneo — sem baseline não há como saber.
"""

from dataclasses import dataclass

from app.domain.text import normalize_text

_CATEGORIA_FALLBACK = "Outros"
_CONFIANCA_ALTA = 0.9
_CONFIANCA_BAIXA = 0.2

_PALAVRAS_CHAVE: dict[str, str] = {
    # Alimentação
    "restaurante": "Alimentação",
    "lanchonete": "Alimentação",
    "ifood": "Alimentação",
    "pizza": "Alimentação",
    "lanche": "Alimentação",
    "almoco": "Alimentação",
    "jantar": "Alimentação",
    # Mercado
    "mercado": "Mercado",
    "supermercado": "Mercado",
    "atacadao": "Mercado",
    "hortifruti": "Mercado",
    "feira": "Mercado",
    # Transporte
    "uber": "Transporte",
    "99": "Transporte",
    "gasolina": "Transporte",
    "combustivel": "Transporte",
    "onibus": "Transporte",
    "metro": "Transporte",
    "estacionamento": "Transporte",
    # Moradia
    "aluguel": "Moradia",
    "condominio": "Moradia",
    "energia": "Moradia",
    "internet": "Moradia",
    "agua": "Moradia",
    # Saúde
    "farmacia": "Saúde",
    "consulta": "Saúde",
    "exame": "Saúde",
    "remedio": "Saúde",
    "medico": "Saúde",
    "dentista": "Saúde",
    # Educação
    "curso": "Educação",
    "faculdade": "Educação",
    "escola": "Educação",
    # Lazer
    "cinema": "Lazer",
    "show": "Lazer",
    "viagem": "Lazer",
    "parque": "Lazer",
    # Vestuário
    "roupa": "Vestuário",
    "sapato": "Vestuário",
    "camisa": "Vestuário",
    # Assinaturas
    "netflix": "Assinaturas",
    "spotify": "Assinaturas",
    "assinatura": "Assinaturas",
}


@dataclass(frozen=True)
class CategorySuggestion:
    category: str
    confidence: float


def suggest_category(description: str) -> CategorySuggestion:
    """Sugere uma categoria a partir de palavras-chave na descrição.

    Cada palavra-chave encontrada conta um ponto para a categoria a que pertence; a
    categoria com mais pontos vence. Sem nenhuma pista reconhecida, cai em "Outros" com
    confiança baixa. Função pura — mesma entrada, mesma saída, sempre.
    """
    texto = normalize_text(description)

    pontuacao: dict[str, int] = {}
    for palavra, categoria in _PALAVRAS_CHAVE.items():
        if palavra in texto:
            pontuacao[categoria] = pontuacao.get(categoria, 0) + 1

    if not pontuacao:
        return CategorySuggestion(category=_CATEGORIA_FALLBACK, confidence=_CONFIANCA_BAIXA)

    categoria_vencedora = max(pontuacao.items(), key=lambda item: item[1])[0]
    return CategorySuggestion(category=categoria_vencedora, confidence=_CONFIANCA_ALTA)
