import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAMADAS_PROIBIDAS = [PROJECT_ROOT / "app" / "domain", PROJECT_ROOT / "app" / "tools"]


def _importa_modulo(arquivo: Path, prefixo: str) -> bool:
    partes_prefixo = prefixo.split(".")
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[: len(partes_prefixo)] == partes_prefixo for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.split(".")[: len(partes_prefixo)] == partes_prefixo
        ):
            return True
    return False


def _importa_pydantic_ai(arquivo: Path) -> bool:
    return _importa_modulo(arquivo, "pydantic_ai")


@pytest.mark.unit
def test_domain_e_tools_nao_importam_framework_de_agente() -> None:
    ofensores = [
        str(arquivo.relative_to(PROJECT_ROOT))
        for camada in CAMADAS_PROIBIDAS
        for arquivo in camada.rglob("*.py")
        if _importa_pydantic_ai(arquivo)
    ]

    assert ofensores == [], f"RF-86 violado por: {ofensores}"


@pytest.mark.unit
def test_app_adapters_e_o_unico_lugar_que_importa_pydantic_ai() -> None:
    diretorio_adapters = PROJECT_ROOT / "app" / "adapters"
    outras_camadas = [
        camada
        for camada in (PROJECT_ROOT / "app").iterdir()
        if camada.is_dir() and camada != diretorio_adapters
    ]

    ofensores = [
        str(arquivo.relative_to(PROJECT_ROOT))
        for camada in outras_camadas
        for arquivo in camada.rglob("*.py")
        if _importa_pydantic_ai(arquivo)
    ]
    assert ofensores == [], f"RF-86 violado por: {ofensores}"

    assert any(_importa_pydantic_ai(arquivo) for arquivo in diretorio_adapters.rglob("*.py")), (
        "nenhum arquivo em app/adapters importa pydantic_ai — teste não prova nada"
    )


@pytest.mark.unit
def test_nucleo_do_agente_nao_importa_o_adapter_do_telegram() -> None:
    # RNF-10: Telegram fica isolado atrás do ChannelMessage — domain, tools e o núcleo do
    # agente (agent.py, conversation.py, tools.py, llm.py, prompts.py) não sabem que ele
    # existe. Só app/adapters/telegram.py e app/telegram_poller.py podem falar com ele.
    nucleo = [
        *CAMADAS_PROIBIDAS,
        PROJECT_ROOT / "app" / "adapters" / "agent.py",
        PROJECT_ROOT / "app" / "adapters" / "conversation.py",
        PROJECT_ROOT / "app" / "adapters" / "tools.py",
        PROJECT_ROOT / "app" / "adapters" / "llm.py",
        PROJECT_ROOT / "app" / "adapters" / "prompts.py",
    ]
    arquivos = [
        arquivo
        for caminho in nucleo
        for arquivo in (caminho.rglob("*.py") if caminho.is_dir() else [caminho])
        if arquivo.exists()
    ]

    ofensores = [
        str(arquivo.relative_to(PROJECT_ROOT))
        for arquivo in arquivos
        if _importa_modulo(arquivo, "app.adapters.telegram")
        or _importa_modulo(arquivo, "app.telegram_poller")
    ]
    assert ofensores == [], f"RNF-10 violado por: {ofensores}"
