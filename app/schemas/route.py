from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.route import RouteStatus


class RoutePointCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    note: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    order: Optional[int] = None


class RoutePointUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    note: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    order: Optional[int] = None


class RoutePointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order: int
    title: str
    note: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class PersonalRouteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class PersonalRouteUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status: Optional[RouteStatus] = None


class PersonalRouteListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: RouteStatus
    points_count: int
    created_at: datetime
    updated_at: datetime


class PersonalRouteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: RouteStatus
    points: List[RoutePointRead]
    created_at: datetime
    updated_at: datetime


class RouteReorderRequest(BaseModel):
    point_ids: List[int] = Field(min_length=1)
