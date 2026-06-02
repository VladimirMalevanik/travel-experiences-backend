import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class JourneyType(str, enum.Enum):
    experience = "experience"
    route = "route"


class JourneyStatus(str, enum.Enum):
    started = "started"
    completed = "completed"


class Journey(Base):
    __tablename__ = "journeys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    journey_type: Mapped[JourneyType] = mapped_column(
        Enum(JourneyType, name="journey_type"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[JourneyStatus] = mapped_column(
        Enum(JourneyStatus, name="journey_status"), nullable=False, default=JourneyStatus.started
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    progress: Mapped[list["JourneyProgress"]] = relationship(
        back_populates="journey", cascade="all, delete-orphan"
    )


class JourneyProgress(Base):
    __tablename__ = "journey_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journey_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    point_id: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    journey: Mapped["Journey"] = relationship(back_populates="progress")
