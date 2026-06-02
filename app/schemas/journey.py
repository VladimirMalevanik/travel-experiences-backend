from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models.journey import JourneyStatus, JourneyType


class RouteJourneyProgressRequest(BaseModel):
    point_id: int


class JourneyProgressPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    point_id: int
    completed_at: datetime


class JourneyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    journey_type: JourneyType
    target_id: int
    status: JourneyStatus
    started_at: datetime
    updated_at: datetime
    finished_at: Optional[datetime] = None
    completed_points: List[JourneyProgressPointRead]
