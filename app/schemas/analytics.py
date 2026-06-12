from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class AnalyticsEventIn(BaseModel):
    event_name: str = Field(min_length=1, max_length=100)
    session_id: str = Field(min_length=1, max_length=255)
    source_app: str = Field(min_length=1, max_length=50)
    entity_type: Optional[str] = Field(default=None, max_length=50)
    entity_id: Optional[int] = None
    event_version: int = Field(default=1, ge=1)
    occurred_at: Optional[datetime] = None
    event_timestamp: Optional[datetime] = None
    payload: Optional[Dict[str, Any]] = None


class AnalyticsEventsBatch(BaseModel):
    events: List[AnalyticsEventIn] = Field(min_length=1)


class AnalyticsEventsAccepted(BaseModel):
    accepted: int


class AnalyticsBasicReport(BaseModel):
    total_events: int
    events_by_name: Dict[str, int]


AnalyticsEventsRequest = Union[AnalyticsEventsBatch, AnalyticsEventIn]
