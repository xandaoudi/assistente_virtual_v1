"""Política de janela do histórico de conversa (RF-65, §3.3.5).

Sem uma janela, cada mensagem gravada é paga de novo em toda requisição seguinte à LLM — a
conversa fica mais cara a cada turno. `apply_message_window` mantém só as últimas
`max_messages` mensagens; a janela é aplicada na leitura, não na escrita — nada é apagado
do histórico persistido.
"""

import uuid

from app.domain.repositories import ConversationRepository


def apply_message_window(
    messages: list[dict[str, object]], max_messages: int
) -> list[dict[str, object]]:
    if max_messages <= 0:
        return []
    return messages[-max_messages:]


class ConversationService:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    async def load_recent_history(
        self, user_id: uuid.UUID, max_messages: int
    ) -> list[dict[str, object]]:
        mensagens = await self._repository.list_messages(user_id)
        return apply_message_window(mensagens, max_messages)

    async def append_messages(self, user_id: uuid.UUID, messages: list[dict[str, object]]) -> None:
        if not messages:
            return
        await self._repository.append_messages(user_id, messages)
