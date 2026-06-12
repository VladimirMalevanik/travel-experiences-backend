from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.complaint import ComplaintStatus


class ComplaintCreate(BaseModel):
    target_type: str = Field(default="experience", min_length=1, max_length=50)
    target_id: int
    reason_code: str = Field(min_length=1, max_length=100)
    reason_text: Optional[str] = None


class ComplaintResolveRequest(BaseModel):
    status: ComplaintStatus = ComplaintStatus.resolved
    resolution_text: Optional[str] = None
    reason_text: Optional[str] = None

    @model_validator(mode="after")
    def _require_text(self) -> "ComplaintResolveRequest":
        if self.status not in (ComplaintStatus.resolved, ComplaintStatus.rejected):
            raise ValueError("status must be resolved or rejected")
        if not (self.resolution_text or self.reason_text):
            raise ValueError("resolution_text or reason_text is required")
        return self


class ComplaintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporter_user_id: int
    target_type: str
    target_id: int
    reason_code: str
    reason_text: Optional[str] = None
    status: ComplaintStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    moderator_id: Optional[int] = None
    resolution_text: Optional[str] = None


class ComplaintListResponse(BaseModel):
    items: List[ComplaintRead]
    total: int
