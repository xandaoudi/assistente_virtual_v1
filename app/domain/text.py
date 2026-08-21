"""Normalização de texto compartilhada pelo domínio (busca textual e categorização)."""

import unicodedata


def normalize_text(texto: str) -> str:
    """Remove acentos e ignora maiúsculas, para que "Almoço"/"almoco" e "MERCADO"/"mercado"
    sejam equivalentes na busca e no casamento de palavras-chave."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.casefold()
