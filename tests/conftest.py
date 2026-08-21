import os

import pytest

os.environ.setdefault("APP_ENV", "test")


@pytest.fixture(autouse=True, scope="session")
def _block_real_llm_calls() -> None:
    """Impede chamada real à LLM em qualquer teste (RNF-36)."""
    import pydantic_ai.models

    pydantic_ai.models.ALLOW_MODEL_REQUESTS = False
