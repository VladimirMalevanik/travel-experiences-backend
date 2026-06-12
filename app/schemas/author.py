from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.experience import ExperienceStatus


class ExperiencePointCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    order: Optional[int] = None


class ExperiencePointUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    order: Optional[int] = None


class AuthorExperienceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    short_description: Optional[str] = Field(default=None, max_length=500)
    full_description: Optional[str] = None
    city: Optional[str] = Field(default=None, max_length=100)
    duration_minutes: Optional[int] = Field(default=None, ge=0)
    price: float = Field(default=0.0, ge=0)
    restrictions: Optional[str] = None
    points: List[ExperiencePointCreate] = Field(default_factory=list)


class AuthorExperienceUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    short_description: Optional[str] = Field(default=None, max_length=500)
    full_description: Optional[str] = None
    city: Optional[str] = Field(default=None, max_length=100)
    duration_minutes: Optional[int] = Field(default=None, ge=0)
    price: Optional[float] = Field(default=None, ge=0)
    restrictions: Optional[str] = None
    points: Optional[List[ExperiencePointUpdate]] = None


class AuthorExperiencePoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order: int
    title: str
    description: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class AuthorExperienceListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    city: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: float
    status: ExperienceStatus


class AuthorExperienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: Optional[int] = None
    title: str
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    city: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: float
    restrictions: Optional[str] = None
    status: ExperienceStatus
    moderation_reason_code: Optional[str] = None
    moderation_reason_text: Optional[str] = None
    points: List[AuthorExperiencePoint]
