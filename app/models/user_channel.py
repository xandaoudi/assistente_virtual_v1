import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UserChannel(Base):
    """Vínculo canal -> conta (RF-02, RF-03). `UNIQUE` em (channel, external_id) é a trava
    que impede duas contas para o mesmo `chat_id` sob criação concorrente (T3.8)."""

    __tablename__ = "user_channels"
    __table_args__ = (
        UniqueConstraint("channel", "external_id", name="uq_user_channels_channel_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(120))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
