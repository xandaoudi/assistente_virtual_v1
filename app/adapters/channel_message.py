"""Formato canônico de mensagem recebida por qualquer canal (RNF-10, OBJ-05).

Telegram, WhatsApp e Web convertem seu formato nativo para `ChannelMessage` antes de
qualquer processamento — o agente e o domínio nunca veem um `Update` do Telegram.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ChannelMessage:
    channel: str
    external_user_id: str
    text: str | None
    media: str | None
    timestamp: datetime
    message_id: str
