import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class ExperienceStatus(str, enum.Enum):
    draft = "draft"
    on_moderation = "on_moderation"
    published = "published"
    rejected = "rejected"


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    full_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    restrictions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ExperienceStatus] = mapped_column(
        Enum(ExperienceStatus, name="experience_status"),
        nullable=False,
        default=ExperienceStatus.draft,
        index=True,
    )
    moderation_reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    moderation_reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    points: Mapped[list["ExperiencePoint"]] = relationship(
        back_populates="experience", cascade="all, delete-orphan", order_by="ExperiencePoint.order"
    )


class ExperiencePoint(Base):
    __tablename__ = "experience_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experience_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    experience: Mapped["Experience"] = relationship(back_populates="points")
