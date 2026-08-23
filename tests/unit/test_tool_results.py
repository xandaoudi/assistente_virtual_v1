import pytest

from app.domain.errors import DomainError
from app.tools.results import ErrorCode, ToolError, ToolSuccess, run_safely

pytestmark = pytest.mark.unit


async def _ok() -> str:
    return "valor"


async def _falha_dominio() -> str:
    raise DomainError("categoria não encontrada para este usuário")


_EXCECOES_INESPERADAS = [
    ValueError("boom"),
    KeyError("id_interno_da_linha"),
    RuntimeError("SELECT * FROM transactions WHERE ..."),
    ZeroDivisionError("division by zero"),
]


@pytest.mark.asyncio
async def test_sucesso_carrega_dados_e_e_distinguivel_do_erro_pelo_tipo() -> None:
    resultado = await run_safely(_ok())

    assert isinstance(resultado, ToolSuccess)
    assert not isinstance(resultado, ToolError)
    assert resultado.data == "valor"


@pytest.mark.asyncio
async def test_erro_carrega_codigo_e_mensagem() -> None:
    resultado = await run_safely(_falha_dominio())

    assert isinstance(resultado, ToolError)
    assert not isinstance(resultado, ToolSuccess)
    assert resultado.code == ErrorCode.BUSINESS_RULE_VIOLATION
    assert resultado.message


@pytest.mark.asyncio
async def test_domain_error_conhecido_vira_business_rule_violation() -> None:
    resultado = await run_safely(_falha_dominio())

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.BUSINESS_RULE_VIOLATION
    assert resultado.message == "categoria não encontrada para este usuário"


@pytest.mark.asyncio
@pytest.mark.parametrize("excecao", _EXCECOES_INESPERADAS)
async def test_excecao_inesperada_vira_internal_error_sem_vazar_detalhe(
    excecao: Exception,
) -> None:
    async def _levanta() -> str:
        raise excecao

    resultado = await run_safely(_levanta())

    assert isinstance(resultado, ToolError)
    assert resultado.code == ErrorCode.INTERNAL_ERROR
    assert "Traceback" not in resultado.message
    assert "sqlalchemy" not in resultado.message.lower()
    assert "select" not in resultado.message.lower()
    assert "id_interno_da_linha" not in resultado.message
    assert str(excecao) not in resultado.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "excecao", [*_EXCECOES_INESPERADAS, DomainError("categoria não encontrada")]
)
async def test_nenhuma_excecao_propaga_atraves_do_envelope(excecao: Exception) -> None:
    async def _levanta() -> str:
        raise excecao

    # Não deve levantar — se propagar, o teste falha com a própria exceção.
    resultado = await run_safely(_levanta())
    assert isinstance(resultado, ToolSuccess | ToolError)
