import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAMADAS_PROIBIDAS = [PROJECT_ROOT / "app" / "domain", PROJECT_ROOT / "app" / "tools"]


def _importa_pydantic_ai(arquivo: Path) -> bool:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] == "pydantic_ai" for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.split(".")[0] == "pydantic_ai"
        ):
            return True
    return False


@pytest.mark.unit
def test_domain_e_tools_nao_importam_framework_de_agente() -> None:
    ofensores = [
        str(arquivo.relative_to(PROJECT_ROOT))
        for camada in CAMADAS_PROIBIDAS
        for arquivo in camada.rglob("*.py")
        if _importa_pydantic_ai(arquivo)
    ]

    assert ofensores == [], f"RF-86 violado por: {ofensores}"
