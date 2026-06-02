from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.review import ReviewTargetType


class ReviewCreate(BaseModel):
    target_type: ReviewTargetType
    target_id: int
    journey_id: int
    rating: int = Field(ge=1, le=5)
    text: Optional[str] = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    target_type: ReviewTargetType
    target_id: int
    journey_id: Optional[int] = None
    rating: int
    text: Optional[str] = None
    created_at: datetime
