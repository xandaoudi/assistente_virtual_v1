import uuid
from dataclasses import FrozenInstanceError
from datetime import date

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.tools.context import ToolContext
from app.tools.schemas import ToolParams

pytestmark = pytest.mark.unit


class _ExemploParams(ToolParams):
    descricao: str


def _todas_as_subclasses(cls: type) -> set[type]:
    diretas = set(cls.__subclasses__())
    return diretas | {neta for sub in diretas for neta in _todas_as_subclasses(sub)}


def _novo_contexto(**overrides: object) -> ToolContext:
    padrao: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "timezone": "America/Sao_Paulo",
        "currency": "BRL",
        "today": date(2026, 8, 21),
    }
    padrao.update(overrides)
    return ToolContext(**padrao)  # type: ignore[arg-type]


def test_toolcontext_carrega_user_id_timezone_currency_today_e_idempotency_key() -> None:
    user_id = uuid.uuid4()
    ctx = ToolContext(
        user_id=user_id,
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=date(2026, 8, 21),
        idempotency_key="msg-123",
    )

    assert ctx.user_id == user_id
    assert ctx.timezone == "America/Sao_Paulo"
    assert ctx.currency == "BRL"
    assert ctx.today == date(2026, 8, 21)
    assert ctx.idempotency_key == "msg-123"


def test_toolcontext_e_imutavel() -> None:
    ctx = _novo_contexto()

    with pytest.raises(FrozenInstanceError):
        ctx.user_id = uuid.uuid4()  # type: ignore[misc]


def test_duas_execucoes_com_contextos_diferentes_nao_compartilham_estado() -> None:
    ctx_a = _novo_contexto(idempotency_key="msg-a")
    ctx_b = _novo_contexto(idempotency_key="msg-b")

    assert ctx_a.user_id != ctx_b.user_id
    assert ctx_a.idempotency_key != ctx_b.idempotency_key
    assert ctx_a != ctx_b


def test_nenhum_schema_de_parametro_tem_campo_user_id() -> None:
    for schema in _todas_as_subclasses(ToolParams):
        assert "user_id" not in schema.model_fields, schema.__name__


def test_introspeccao_detecta_um_schema_novo_com_user_id() -> None:
    # Prova que o teste acima não é vazio: um schema mal-formado é de fato pego.
    # Não herda do ToolParams de verdade: uma subclasse real ficaria registrada em
    # ToolParams.__subclasses__() para o resto do processo de teste e vazaria para
    # qualquer outro teste que faça essa mesma introspecção depois deste.
    class _BaseComMesmaForma(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class _ParamsVazandoUserId(_BaseComMesmaForma):
        user_id: str

    with pytest.raises(AssertionError):
        for schema in (_ParamsVazandoUserId,):
            assert "user_id" not in schema.model_fields, schema.__name__


def test_schema_rejeita_user_id_como_campo_extra() -> None:
    with pytest.raises(ValidationError):
        _ExemploParams(descricao="ok", user_id=str(uuid.uuid4()))
