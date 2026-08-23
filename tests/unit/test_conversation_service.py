"""Política de janela do histórico de conversa (T3.5, RF-65, §3.3.5)."""

import uuid

import pytest

from app.domain.conversation_service import ConversationService, apply_message_window

pytestmark = pytest.mark.unit


def _mensagens(n: int) -> list[dict[str, object]]:
    return [{"seq": i} for i in range(n)]


def test_janela_mantem_apenas_as_ultimas_n_mensagens() -> None:
    resultado = apply_message_window(_mensagens(30), max_messages=20)

    assert resultado == _mensagens(30)[-20:]
    assert len(resultado) == 20


def test_janela_nao_afeta_historico_menor_que_o_limite() -> None:
    resultado = apply_message_window(_mensagens(3), max_messages=20)

    assert resultado == _mensagens(3)


def test_janela_com_limite_zero_devolve_historico_vazio() -> None:
    assert apply_message_window(_mensagens(5), max_messages=0) == []


def test_a_conversa_nao_cresce_indefinidamente() -> None:
    # Critério de aceite da T3.5: por maior que o histórico persistido, o que sai da janela
    # nunca passa do teto definido.
    for tamanho_persistido in (0, 1, 20, 21, 500, 10_000):
        resultado = apply_message_window(_mensagens(tamanho_persistido), max_messages=20)
        assert len(resultado) <= 20


class _RepositorioFalso:
    def __init__(self) -> None:
        self.mensagens: dict[uuid.UUID, list[dict[str, object]]] = {}

    async def append_messages(self, user_id: uuid.UUID, messages: list[dict[str, object]]) -> None:
        self.mensagens.setdefault(user_id, []).extend(messages)

    async def list_messages(self, user_id: uuid.UUID) -> list[dict[str, object]]:
        return list(self.mensagens.get(user_id, []))


@pytest.mark.asyncio
async def test_conversation_service_aplica_a_janela_ao_carregar_historico() -> None:
    repo = _RepositorioFalso()
    user_id = uuid.uuid4()
    await repo.append_messages(user_id, _mensagens(30))
    service = ConversationService(repo)

    historico = await service.load_recent_history(user_id, max_messages=20)

    assert historico == _mensagens(30)[-20:]


@pytest.mark.asyncio
async def test_conversation_service_nao_grava_lista_vazia() -> None:
    repo = _RepositorioFalso()
    user_id = uuid.uuid4()
    service = ConversationService(repo)

    await service.append_messages(user_id, [])

    assert await repo.list_messages(user_id) == []


@pytest.mark.asyncio
async def test_conversation_service_grava_mensagens_novas() -> None:
    repo = _RepositorioFalso()
    user_id = uuid.uuid4()
    service = ConversationService(repo)

    await service.append_messages(user_id, _mensagens(2))

    assert await repo.list_messages(user_id) == _mensagens(2)
