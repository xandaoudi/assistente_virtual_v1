"""T3.6 — laço de longa duração do poller: avanço de offset e recuperação de falha de rede."""

from collections.abc import Callable

import pytest

from app.adapters.channel_message import ChannelMessage
from app.adapters.telegram import TelegramApiError, run_polling_loop

pytestmark = pytest.mark.unit


def _update(update_id: int) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": 1, "type": "private"},
            "date": 1735000000,
            "text": f"mensagem {update_id}",
        },
    }


class _FonteFalsa:
    def __init__(self, respostas: list[list[dict[str, object]] | Exception]) -> None:
        self._respostas = respostas
        self.offsets_recebidos: list[int] = []

    async def get_updates(self, offset: int) -> list[dict[str, object]]:
        self.offsets_recebidos.append(offset)
        resposta = self._respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def _limita_voltas(maximo: int) -> Callable[[], bool]:
    contador = {"voltas": 0}

    def continuar() -> bool:
        contador["voltas"] += 1
        return contador["voltas"] <= maximo

    return continuar


@pytest.mark.asyncio
async def test_poller_avanca_offset_e_nao_reprocessa_update_ja_consumido() -> None:
    fonte = _FonteFalsa([[_update(100), _update(101)], [], []])
    recebidas: list[ChannelMessage] = []
    continuar = _limita_voltas(3)

    async def handler(mensagem: ChannelMessage) -> None:
        recebidas.append(mensagem)

    async def sem_espera(segundos: float) -> None:
        return None

    await run_polling_loop(
        fonte, handler, initial_offset=0, sleep=sem_espera, should_continue=continuar
    )

    # offset avança para 102 (maior update_id + 1) e permanece lá enquanto não há novidade
    # — nunca volta a pedir os updates 100/101 já processados.
    assert fonte.offsets_recebidos == [0, 102, 102]
    assert [m.message_id for m in recebidas] == ["100", "101"]


@pytest.mark.asyncio
async def test_poller_trata_queda_de_rede_sem_morrer_e_espera_crescente() -> None:
    fonte = _FonteFalsa([TelegramApiError("timeout"), TelegramApiError("timeout"), []])
    esperas: list[float] = []
    continuar = _limita_voltas(3)

    async def handler(mensagem: ChannelMessage) -> None:
        pass

    async def registra_espera(segundos: float) -> None:
        esperas.append(segundos)

    await run_polling_loop(
        fonte, handler, initial_offset=0, sleep=registra_espera, should_continue=continuar
    )

    assert len(esperas) == 2
    assert esperas[1] > esperas[0], "a espera entre tentativas precisa crescer"


@pytest.mark.asyncio
async def test_poller_volta_a_espera_inicial_apos_sucesso() -> None:
    fonte = _FonteFalsa(
        [TelegramApiError("timeout"), [], TelegramApiError("timeout"), TelegramApiError("timeout")]
    )
    esperas: list[float] = []
    continuar = _limita_voltas(4)

    async def handler(mensagem: ChannelMessage) -> None:
        pass

    async def registra_espera(segundos: float) -> None:
        esperas.append(segundos)

    await run_polling_loop(
        fonte, handler, initial_offset=0, sleep=registra_espera, should_continue=continuar
    )

    # 1ª falha, depois sucesso (não gera espera), depois 2ª e 3ª falhas em sequência.
    # A espera da 2ª falha volta ao valor inicial — o sucesso no meio reseta o backoff, não
    # continua crescendo a partir da 1ª falha.
    assert esperas == pytest.approx([1.0, 1.0, 2.0])
