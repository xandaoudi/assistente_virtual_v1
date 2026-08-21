"""Onboarding mínimo de usuário — o fluxo completo (RF-01 a RF-06) é a Etapa 4."""

import uuid

from app.models.user import User

DEFAULT_TIMEZONE = "America/Sao_Paulo"
DEFAULT_CURRENCY = "BRL"
DEFAULT_LOCALE = "pt_BR"


class UserService:
    def create_user(
        self,
        name: str,
        *,
        timezone: str | None = None,
        currency: str | None = None,
        locale: str | None = None,
    ) -> User:
        """Monta um novo `User` com os padrões do app quando não informados explicitamente.

        O `id` é gerado aqui (não deixado para o default da coluna) para que registros
        relacionados — como as categorias padrão do RF-45 — possam referenciá-lo antes de
        qualquer flush no banco.
        """
        return User(
            id=uuid.uuid4(),
            name=name,
            timezone=timezone or DEFAULT_TIMEZONE,
            currency=currency or DEFAULT_CURRENCY,
            locale=locale or DEFAULT_LOCALE,
        )
