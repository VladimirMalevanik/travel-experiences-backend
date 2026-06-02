from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.order import (
    OrderRead,
    PaymentInitRead,
    PaymentWebhookRead,
    PaymentWebhookRequest,
)
from app.services.auth import require_roles
from app.services.payments import (
    InvalidStatusTransition,
    PaymentError,
    build_payment_url,
    get_order_for_user,
    init_payment,
    process_webhook,
)

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger("app.payments")


def _user_only(current_user: User = Depends(require_roles(UserRole.User))) -> User:
    return current_user


@router.post("/{order_id}/init", response_model=PaymentInitRead)
def init_payment_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> PaymentInitRead:
    order = get_order_for_user(db, order_id, current_user.id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    try:
        order = init_payment(db, order)
    except PaymentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)

    return PaymentInitRead(
        order_id=order.id,
        status=order.status,
        payment_url=build_payment_url(order.id),
        provider="mock",
    )


@router.post("/webhook", response_model=PaymentWebhookRead)
def payment_webhook_endpoint(
    payload: PaymentWebhookRequest,
    db: Session = Depends(get_db),
    x_mock_payment_secret: Optional[str] = Header(default=None, alias="X-Mock-Payment-Secret"),
) -> PaymentWebhookRead:
    if not x_mock_payment_secret or x_mock_payment_secret != settings.MOCK_PAYMENT_WEBHOOK_SECRET:
        logger.warning(
            "payment_webhook_unauthorized order_id=%s provider_event_id=%s",
            payload.order_id,
            payload.provider_event_id,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid webhook secret")

    logger.info(
        "payment_webhook_received order_id=%s provider_event_id=%s status=%s",
        payload.order_id,
        payload.provider_event_id,
        payload.status,
    )

    try:
        order, access_granted, idempotent = process_webhook(
            db, payload.order_id, payload.provider_event_id, payload.status
        )
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except PaymentError as exc:
        if exc.code == "order_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)

    return PaymentWebhookRead(
        order=OrderRead.model_validate(order),
        access_granted=access_granted,
        idempotent=idempotent,
    )
