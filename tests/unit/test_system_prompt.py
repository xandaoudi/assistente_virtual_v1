import re
from pathlib import Path

import pytest

from app.adapters.prompts import PROMPT_PATH, load_system_prompt, read_system_prompt
from app.tools.token_budget import estimate_tokens

pytestmark = pytest.mark.unit

_TETO_TOKENS = 1000

_PADROES_PROIBIDOS = [
    r"://",  # qualquer URL com esquema (http, postgresql, etc.)
    r"(?i)api[_-]?key",
    r"(?i)secret",
    r"(?i)password",
    r"(?i)database_url",
    r"(?i)\bBearer\s",
]


def test_prompt_carrega_do_arquivo_e_nao_esta_vazio() -> None:
    prompt = load_system_prompt()

    assert prompt.strip() != ""


def test_prompt_e_carregado_do_arquivo_versionado() -> None:
    assert PROMPT_PATH.exists()
    assert PROMPT_PATH.read_text(encoding="utf-8").strip() == load_system_prompt()


def test_trocar_o_conteudo_do_arquivo_muda_o_prompt_carregado(tmp_path: Path) -> None:
    arquivo = tmp_path / "system_pt_br.md"
    arquivo.write_text("Conteúdo alternativo de teste.", encoding="utf-8")

    assert read_system_prompt(arquivo) == "Conteúdo alternativo de teste."


def test_prompt_nao_contem_segredo_chave_nem_url_de_infraestrutura() -> None:
    prompt = load_system_prompt()

    for padrao in _PADROES_PROIBIDOS:
        assert not re.search(padrao, prompt), f"prompt contém padrão proibido: {padrao!r}"


def test_deteccao_de_segredo_no_prompt_realmente_funciona(tmp_path: Path) -> None:
    arquivo = tmp_path / "system_pt_br.md"
    arquivo.write_text(
        "Use a chave DATABASE_URL=postgresql://user:pass@host/db para conectar.",
        encoding="utf-8",
    )
    prompt_com_segredo = read_system_prompt(arquivo)

    achados = [padrao for padrao in _PADROES_PROIBIDOS if re.search(padrao, prompt_com_segredo)]

    assert achados, "o teste de segredo não pegaria um prompt com segredo de verdade"


def test_tamanho_do_prompt_esta_abaixo_do_teto_de_tokens() -> None:
    prompt = load_system_prompt()

    tokens = estimate_tokens(prompt)

    assert tokens <= _TETO_TOKENS, f"prompt custa {tokens} tokens (teto: {_TETO_TOKENS})."


def test_deteccao_de_prompt_grande_demais_realmente_funciona() -> None:
    prompt_gigante = "x " * (_TETO_TOKENS * 4)

    assert estimate_tokens(prompt_gigante) > _TETO_TOKENS
