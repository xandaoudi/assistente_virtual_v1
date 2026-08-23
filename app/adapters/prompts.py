"""Carrega o system prompt do agente a partir de arquivo versionado (RNF-11).

O comportamento do agente — escopo, tom, quando perguntar em vez de adivinhar — vive em
`prompts/system_pt_br.md`, não em string no código. Trocar o arquivo muda o comportamento
sem recompilar nada.
"""

from functools import lru_cache
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "system_pt_br.md"


def read_system_prompt(path: Path = PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8").strip()


@lru_cache
def load_system_prompt() -> str:
    return read_system_prompt()
