import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ToolAuditLog(Base):
    """RF-88: quem chamou qual tool, quando, com que resultado — nunca o valor em si (RNF-15).

    `params` já chega redigido (`app.tools.audit.redact_params`); esta tabela nunca deveria
    receber `amount`/`description`/`query` em texto claro.
    """

    __tablename__ = "tool_audit_log"
    __table_args__ = (Index("ix_tool_audit_log_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    tool_name: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, object]] = mapped_column(JSONB)
    result_status: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
