from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.experience import ExperienceStatus


class ExperienceListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    short_description: Optional[str] = None
    city: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: float
    status: ExperienceStatus


class ExperienceListResponse(BaseModel):
    items: List[ExperienceListItem]
    page: int
    size: int
    total: int


class ExperiencePointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order: int
    title: str
    description: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class ExperienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    city: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: float
    restrictions: Optional[str] = None
    status: ExperienceStatus
    purchase_available: bool
    points: List[ExperiencePointRead]


class CatalogConfigRead(BaseModel):
    default_sort: List[str]
    max_page_size: int
    source: str
