"""Resolução de identidade: `chat_id` do canal -> `user_id` interno (RF-02, T3.8).

Onboarding completo (nome, fuso e moeda escolhidos pelo usuário — RF-04) é a Etapa 4; aqui
só o mínimo para o caminho fino da Etapa 3 funcionar: usuário novo nasce com os padrões do
`UserService` e as categorias padrão do RF-45, e cada `(channel, external_id)` mapeia para
exatamente um `user_id`, mesmo sob mensagens concorrentes do mesmo chat.
"""

import uuid

from app.domain.default_categories import build_default_categories
from app.domain.repositories import UserChannelRepository
from app.domain.user_service import UserService

DEFAULT_NEW_USER_NAME = "Novo usuário"


class IdentityService:
    def __init__(
        self, channels: UserChannelRepository, user_service: UserService | None = None
    ) -> None:
        self._channels = channels
        self._user_service = user_service or UserService()

    async def resolve_user_id(self, channel: str, external_id: str) -> uuid.UUID:
        """`chat_id` conhecido resolve direto; `chat_id` novo cria a conta com os padrões."""
        existente = await self._channels.get_user_id(channel, external_id)
        if existente is not None:
            return existente

        user = self._user_service.create_user(DEFAULT_NEW_USER_NAME)
        categories = build_default_categories(user.id)
        return await self._channels.resolve_or_create(channel, external_id, user, categories)
