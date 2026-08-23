"""T3.6 — ChannelMessage canônico e conversão de update do Telegram (RNF-10)."""

from datetime import UTC, datetime

import pytest

from app.adapters.channel_message import ChannelMessage
from app.adapters.telegram import (
    TELEGRAM_MESSAGE_LIMIT,
    UNSUPPORTED_CONTENT_REPLY,
    default_reply_for,
    extract_updates_from_poll_response,
    format_telegram_output,
    parse_telegram_update,
    split_telegram_message,
)

pytestmark = pytest.mark.unit


def _update_de_texto(
    update_id: int = 100, texto: str = "gastei 45 no mercado ontem"
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 42,
            "from": {"id": 987654321, "is_bot": False, "first_name": "Alexandre"},
            "chat": {"id": 987654321, "type": "private"},
            "date": 1735000000,
            "text": texto,
        },
    }


def test_update_de_texto_vira_channel_message_correto() -> None:
    mensagem = parse_telegram_update(_update_de_texto())

    assert mensagem == ChannelMessage(
        channel="telegram",
        external_user_id="987654321",
        text="gastei 45 no mercado ontem",
        media=None,
        timestamp=datetime.fromtimestamp(1735000000, tz=UTC),
        message_id="42",
    )


def test_update_com_figurinha_nao_quebra_e_tem_resposta_educada() -> None:
    update = _update_de_texto()
    del update["message"]["text"]  # type: ignore[index]
    update["message"]["sticker"] = {"file_id": "abc", "type": "regular"}  # type: ignore[index]

    mensagem = parse_telegram_update(update)

    assert mensagem is not None
    assert mensagem.text is None
    assert mensagem.media == "sticker"
    assert default_reply_for(mensagem) == UNSUPPORTED_CONTENT_REPLY


def test_update_com_foto_e_legenda_usa_a_legenda_como_texto() -> None:
    update = _update_de_texto()
    del update["message"]["text"]  # type: ignore[index]
    update["message"]["photo"] = [{"file_id": "abc", "width": 90, "height": 90}]  # type: ignore[index]
    update["message"]["caption"] = "recibo do mercado"  # type: ignore[index]

    mensagem = parse_telegram_update(update)

    assert mensagem is not None
    assert mensagem.text == "recibo do mercado"
    assert mensagem.media == "photo"


@pytest.mark.parametrize(
    "update",
    [
        {},
        {"update_id": 1},
        {"update_id": 1, "message": {}},
        {"update_id": 1, "message": {"chat": {}, "message_id": 1, "date": 1}},
        {"update_id": "nao-e-inteiro", "message": _update_de_texto()["message"]},
        {
            "update_id": 1,
            "message": {"chat": {"id": 1}, "message_id": 1, "date": "nao-e-timestamp"},
        },
        None,
        "isso nao e um dict",
        [1, 2, 3],
    ],
)
def test_update_malformado_e_rejeitado_sem_excecao(update: object) -> None:
    assert parse_telegram_update(update) is None


def test_texto_normal_nao_precisa_de_resposta_padrao() -> None:
    mensagem = parse_telegram_update(_update_de_texto())

    assert mensagem is not None
    assert default_reply_for(mensagem) is None


def test_caracteres_especiais_sao_escapados_para_markdownv2() -> None:
    formatado = format_telegram_output("Você gastou R$ 45,90! Confirma? (sim/não)")

    # Lista oficial de reservados do MarkdownV2: _ * [ ] ( ) ~ ` > # + - = | { } . !
    for caractere in "!()":
        assert f"\\{caractere}" in formatado
    assert "45,90" in formatado  # vírgula não é caractere reservado do MarkdownV2
    assert "?" in formatado and "\\?" not in formatado  # "?" também não é reservado


def test_negrito_duplo_asterisco_vira_negrito_do_telegram() -> None:
    formatado = format_telegram_output("Você gastou **R$ 45,90** no mercado.")

    assert "*R$ 45,90*" in formatado
    assert "**" not in formatado


def test_ponto_final_e_escapado() -> None:
    # "." é reservado no MarkdownV2 — sem escape, o Telegram rejeita a mensagem inteira.
    assert "\\." in format_telegram_output("Registrado.")


def test_resposta_dentro_do_limite_nao_e_dividida() -> None:
    texto = "x" * 100

    assert split_telegram_message(texto) == [texto]


def test_resposta_acima_do_limite_e_dividida_em_partes() -> None:
    texto = "x" * (TELEGRAM_MESSAGE_LIMIT + 500)

    partes = split_telegram_message(texto)

    assert len(partes) > 1
    assert all(len(parte) <= TELEGRAM_MESSAGE_LIMIT for parte in partes)
    assert "".join(partes) == texto


def test_divisao_prefere_cortar_em_quebra_de_linha() -> None:
    bloco = "a" * 4090
    texto = bloco + "\n" + "b" * 200

    partes = split_telegram_message(texto)

    assert partes[0] == bloco
    assert partes[1] == "b" * 200


def test_os_dois_modos_produzem_o_mesmo_channel_message_a_partir_do_mesmo_update() -> None:
    update = _update_de_texto()

    mensagem_via_webhook = parse_telegram_update(update)

    resposta_poll = {"ok": True, "result": [update]}
    updates_extraidos = extract_updates_from_poll_response(resposta_poll)
    assert len(updates_extraidos) == 1
    mensagem_via_poll = parse_telegram_update(updates_extraidos[0])

    assert mensagem_via_webhook is not None
    assert mensagem_via_webhook == mensagem_via_poll
