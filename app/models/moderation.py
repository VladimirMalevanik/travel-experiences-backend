import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ModerationDecisionType(str, enum.Enum):
    publish = "publish"
    reject = "reject"


class ModerationDecision(Base):
    """Журнал решений модерации по впечатлениям (FR-10, FR-14)."""

    __tablename__ = "moderation_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experience_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    moderator_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decision: Mapped[ModerationDecisionType] = mapped_column(
        Enum(ModerationDecisionType, name="moderation_decision_type"), nullable=False
    )
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
