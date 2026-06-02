from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus


class OrderCreate(BaseModel):
    experience_id: int = Field(..., gt=0)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    experience_id: int
    status: OrderStatus
    provider_event_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PaymentInitRead(BaseModel):
    order_id: int
    status: OrderStatus
    payment_url: str
    provider: str = "mock"


WebhookStatus = Literal["paid", "failed"]


class PaymentWebhookRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    provider_event_id: str = Field(..., min_length=1, max_length=255)
    status: WebhookStatus


class PaymentWebhookRead(BaseModel):
    order: OrderRead
    access_granted: bool
    idempotent: bool


class PurchaseAccessRead(BaseModel):
    experience_id: int
    access_granted: bool
    order_id: Optional[int] = None
    granted_at: Optional[datetime] = None
