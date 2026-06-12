from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.experience import ExperienceStatus


class ModerationQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: Optional[int] = None
    title: str
    city: Optional[str] = None
    duration_minutes: Optional[int] = None
    price: float
    status: ExperienceStatus


class ModerationQueueResponse(BaseModel):
    items: List[ModerationQueueItem]
    total: int


class ModerationRejectRequest(BaseModel):
    reason_code: str = Field(min_length=1, max_length=100)
    reason_text: str = Field(min_length=1)


class ModerationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ExperienceStatus
    moderation_reason_code: Optional[str] = None
    moderation_reason_text: Optional[str] = None
