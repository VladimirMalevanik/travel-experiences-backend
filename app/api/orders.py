from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.order import OrderCreate, OrderRead
from app.services.auth import require_roles
from app.services.payments import (
    PaymentError,
    create_order,
    get_order_for_user,
)

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger("app.orders")


def _user_only(current_user: User = Depends(require_roles(UserRole.User))) -> User:
    return current_user


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> OrderRead:
    try:
        order = create_order(db, current_user.id, payload.experience_id)
    except PaymentError as exc:
        if exc.code == "experience_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return OrderRead.model_validate(order)


@router.get("/{order_id}", response_model=OrderRead)
def get_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> OrderRead:
    order = get_order_for_user(db, order_id, current_user.id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderRead.model_validate(order)
