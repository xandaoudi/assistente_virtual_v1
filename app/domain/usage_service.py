"""Consumo de LLM e rate limiting por usuário (RNF-17, RNF-18, T3.10).

Conter custo e abuso desde o primeiro dia: `record` guarda tokens de entrada, de saída e de
cache por interação; `exceeds_rate_limit` decide, antes de qualquer chamada à LLM, se o
usuário já mandou mensagem demais na janela configurada — barato o suficiente para nunca
precisar chamar o modelo só para descobrir que a resposta vai ser "espere um pouco".
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.repositories import UsageLogRepository
from app.models.usage_log import UsageLog


@dataclass(frozen=True)
class RateLimitPolicy:
    messages_per_minute: int
    messages_per_day: int


@dataclass(frozen=True)
class UsageSummary:
    """`cache_hit_ratio=None` quando não há `input_tokens` no período — nada para dividir."""

    requests: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_hit_ratio: float | None


class UsageService:
    def __init__(self, repository: UsageLogRepository) -> None:
        self._repository = repository

    async def record(
        self,
        user_id: uuid.UUID,
        *,
        requests: int,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> UsageLog:
        entry = UsageLog(
            id=uuid.uuid4(),
            user_id=user_id,
            requests=requests,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            created_at=datetime.now(UTC),
        )
        return await self._repository.add(entry)

    async def exceeds_rate_limit(
        self, user_id: uuid.UUID, policy: RateLimitPolicy, *, now: datetime
    ) -> bool:
        """`True` quando o usuário já atingiu o teto por minuto ou por dia (RF-17)."""
        janela_dia = await self._repository.list_by_user(user_id, now - timedelta(days=1), now)
        if len(janela_dia) >= policy.messages_per_day:
            return True

        limiar_minuto = now - timedelta(minutes=1)
        mensagens_no_minuto = sum(1 for entry in janela_dia if entry.created_at >= limiar_minuto)
        return mensagens_no_minuto >= policy.messages_per_minute

    async def summarize(self, user_id: uuid.UUID, start: datetime, end: datetime) -> UsageSummary:
        """Consumo acumulado do usuário no período — o que sustenta o rastreio de custo."""
        entradas = await self._repository.list_by_user(user_id, start, end)
        requests = sum(entry.requests for entry in entradas)
        input_tokens = sum(entry.input_tokens for entry in entradas)
        output_tokens = sum(entry.output_tokens for entry in entradas)
        cache_read_tokens = sum(entry.cache_read_tokens for entry in entradas)
        cache_hit_ratio = (cache_read_tokens / input_tokens) if input_tokens else None
        return UsageSummary(
            requests=requests,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_hit_ratio=cache_hit_ratio,
        )
