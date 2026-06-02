import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class RouteStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class PersonalRoute(Base):
    __tablename__ = "personal_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RouteStatus] = mapped_column(
        Enum(RouteStatus, name="route_status"), nullable=False, default=RouteStatus.draft
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    points: Mapped[list["RoutePoint"]] = relationship(
        back_populates="route", cascade="all, delete-orphan", order_by="RoutePoint.order"
    )


class RoutePoint(Base):
    __tablename__ = "route_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("personal_routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    route: Mapped["PersonalRoute"] = relationship(back_populates="points")
