import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.tools.token_budget import TOOL_PARAMS_SCHEMAS, schema_token_report

pytestmark = pytest.mark.unit

_TETO_TOTAL_TOKENS = 2500
_TETO_DESCRICAO_TOOL = 200
_TETO_DESCRICAO_PARAMETRO = 120


def test_total_do_catalogo_esta_abaixo_do_teto() -> None:
    relatorio = schema_token_report()

    assert relatorio.total <= _TETO_TOTAL_TOKENS, (
        f"Catálogo de tools custa {relatorio.total} tokens (teto: {_TETO_TOTAL_TOKENS})."
    )


def test_relatorio_tem_uma_entrada_por_tool() -> None:
    relatorio = schema_token_report()

    assert set(relatorio.per_tool) == set(TOOL_PARAMS_SCHEMAS)
    assert relatorio.total == sum(relatorio.per_tool.values())


def test_toda_tool_tem_descricao_nao_vazia() -> None:
    for nome, schema_cls in TOOL_PARAMS_SCHEMAS.items():
        descricao = (schema_cls.__doc__ or "").strip()
        assert descricao, f"{nome} não tem descrição (docstring)."


def test_nenhuma_descricao_de_tool_passa_de_200_caracteres() -> None:
    for nome, schema_cls in TOOL_PARAMS_SCHEMAS.items():
        descricao = (schema_cls.__doc__ or "").strip()
        assert len(descricao) <= _TETO_DESCRICAO_TOOL, (
            f"{nome}: descrição com {len(descricao)} caracteres (teto: {_TETO_DESCRICAO_TOOL})."
        )


def test_nenhum_parametro_tem_descricao_acima_de_120_caracteres() -> None:
    for nome, schema_cls in TOOL_PARAMS_SCHEMAS.items():
        for campo, info in schema_cls.model_fields.items():
            descricao = info.description or ""
            assert len(descricao) <= _TETO_DESCRICAO_PARAMETRO, (
                f"{nome}.{campo}: descrição com {len(descricao)} caracteres "
                f"(teto: {_TETO_DESCRICAO_PARAMETRO})."
            )


def test_deteccao_de_descricao_de_parametro_prolixa_realmente_funciona() -> None:
    # Prova que o teste acima não é vazio: uma descrição prolixa é de fato pega.
    # Não herda do ToolParams de verdade: uma subclasse real ficaria registrada em
    # ToolParams.__subclasses__() para o resto do processo de teste e vazaria para
    # qualquer outro teste que faça essa mesma introspecção depois deste.
    class _BaseComMesmaForma(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class _ParamsProlixo(_BaseComMesmaForma):
        campo: str = Field(description="x" * (_TETO_DESCRICAO_PARAMETRO + 1))

    with pytest.raises(AssertionError):
        for info in _ParamsProlixo.model_fields.values():
            assert len(info.description or "") <= _TETO_DESCRICAO_PARAMETRO


def test_deteccao_de_descricao_de_tool_prolixa_realmente_funciona() -> None:
    class _ToolProlixa(BaseModel):
        pass

    _ToolProlixa.__doc__ = "y" * (_TETO_DESCRICAO_TOOL + 1)

    with pytest.raises(AssertionError):
        assert len((_ToolProlixa.__doc__ or "").strip()) <= _TETO_DESCRICAO_TOOL
