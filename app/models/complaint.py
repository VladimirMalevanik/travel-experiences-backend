import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ComplaintStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"
    rejected = "rejected"


class Complaint(Base):
    """Жалобы пользователей на контент/впечатления (FR-11, FR-14)."""

    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ComplaintStatus] = mapped_column(
        Enum(ComplaintStatus, name="complaint_status"),
        nullable=False,
        default=ComplaintStatus.open,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    moderator_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
