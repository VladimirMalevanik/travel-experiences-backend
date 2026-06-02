"""Бизнес-логика заказов и mock-платежей.

Содержит правила переходов статусов заказа и идемпотентную обработку
webhook-событий платежного провайдера (FR-05, FR-06).
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.experience import Experience, ExperienceStatus
from app.models.order import Order, OrderStatus, PurchaseAccess
from app.models.payment import PaymentWebhookEvent

logger = logging.getLogger("app.payments")


# --- Status transitions ---

# Разрешенные переходы статусов заказа (FR-05).
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.created: {OrderStatus.pending, OrderStatus.paid, OrderStatus.failed},
    OrderStatus.pending: {OrderStatus.paid, OrderStatus.failed},
    OrderStatus.paid: {OrderStatus.refunded},
    OrderStatus.failed: set(),
    OrderStatus.refunded: set(),
}

FINAL_STATUSES: set[OrderStatus] = {
    OrderStatus.paid,
    OrderStatus.failed,
    OrderStatus.refunded,
}


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    if current == target:
        return False
    return target in ALLOWED_TRANSITIONS.get(current, set())


# --- Errors ---

class PaymentError(Exception):
    """Базовая бизнес-ошибка платежного домена."""

    def __init__(self, message: str, code: str = "payment_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class InvalidStatusTransition(PaymentError):
    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        super().__init__(
            f"invalid status transition: {current.value} -> {target.value}",
            code="invalid_status_transition",
        )


# --- Orders ---

def create_order(db: Session, user_id: int, experience_id: int) -> Order:
    """Создание заказа. Бросает PaymentError при бизнес-нарушении.

    Не выдает PurchaseAccess (FR-04 / FR-05).
    """
    experience = db.get(Experience, experience_id)
    if experience is None:
        raise PaymentError("experience not found", code="experience_not_found")
    if experience.status != ExperienceStatus.published:
        raise PaymentError(
            "experience is not available for purchase", code="experience_not_published"
        )

    order = Order(
        user_id=user_id,
        experience_id=experience_id,
        status=OrderStatus.created,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    logger.info(
        "order_created user_id=%s order_id=%s experience_id=%s",
        user_id,
        order.id,
        experience_id,
    )
    return order


def get_order_for_user(db: Session, order_id: int, user_id: int) -> Optional[Order]:
    """Возвращает order только если он принадлежит пользователю.

    Чужие или несуществующие заказы возвращаются как None (вызывающий
    превращает это в 404, чтобы не раскрывать существование чужого объекта).
    """
    order = db.get(Order, order_id)
    if order is None:
        return None
    if order.user_id != user_id:
        logger.info(
            "invalid_access_attempt user_id=%s order_id=%s reason=foreign_order",
            user_id,
            order_id,
        )
        return None
    return order


def build_payment_url(order_id: int) -> str:
    return f"{settings.MOCK_PAYMENT_BASE_URL}/{order_id}"


def init_payment(db: Session, order: Order) -> Order:
    """Перевод заказа в pending. Идемпотентно для status=pending."""
    if order.status == OrderStatus.pending:
        logger.info(
            "payment_initialized user_id=%s order_id=%s status=%s idempotent=1",
            order.user_id,
            order.id,
            order.status.value,
        )
        return order

    if order.status == OrderStatus.created:
        _transition(db, order, OrderStatus.pending)
        db.commit()
        db.refresh(order)
        logger.info(
            "payment_initialized user_id=%s order_id=%s status=%s",
            order.user_id,
            order.id,
            order.status.value,
        )
        return order

    if order.status == OrderStatus.paid:
        raise PaymentError("order already paid", code="order_already_paid")

    # failed / refunded
    raise PaymentError(
        "payment cannot be initialized for this status",
        code="payment_init_not_allowed",
    )


# --- Webhook ---

def process_webhook(
    db: Session,
    order_id: int,
    provider_event_id: str,
    webhook_status: str,
) -> Tuple[Order, bool, bool]:
    """Обработка webhook-события. Возвращает (order, access_granted, idempotent).

    Идемпотентность реализована через таблицу payment_webhook_events:
    повторный вызов с тем же provider_event_id не меняет статус и не создает
    повторный PurchaseAccess.
    """
    # 1) идемпотентность по provider_event_id
    existing_event = (
        db.query(PaymentWebhookEvent)
        .filter(PaymentWebhookEvent.provider_event_id == provider_event_id)
        .first()
    )

    order = db.get(Order, order_id)
    if order is None:
        raise PaymentError("order not found", code="order_not_found")

    if existing_event is not None:
        # повторный event — финальное состояние не меняем
        access = _get_access(db, order)
        logger.info(
            "payment_webhook_idempotent order_id=%s provider_event_id=%s",
            order.id,
            provider_event_id,
        )
        return order, access is not None, True

    if webhook_status not in ("paid", "failed"):
        raise PaymentError("invalid webhook status", code="invalid_status")

    target = OrderStatus.paid if webhook_status == "paid" else OrderStatus.failed

    if not can_transition(order.status, target):
        raise InvalidStatusTransition(order.status, target)

    old_status = order.status
    order.status = target
    order.provider_event_id = provider_event_id

    access_granted = False
    if target == OrderStatus.paid:
        access = _get_access(db, order)
        if access is None:
            access = PurchaseAccess(
                user_id=order.user_id,
                experience_id=order.experience_id,
                order_id=order.id,
            )
            db.add(access)
            logger.info(
                "access_granted user_id=%s order_id=%s experience_id=%s",
                order.user_id,
                order.id,
                order.experience_id,
            )
        access_granted = True

    event = PaymentWebhookEvent(
        provider_event_id=provider_event_id,
        order_id=order.id,
        status=target.value,
        result="processed",
    )
    db.add(event)

    db.commit()
    db.refresh(order)

    logger.info(
        "payment_status_changed order_id=%s old_status=%s new_status=%s",
        order.id,
        old_status.value,
        target.value,
    )
    return order, access_granted, False


# --- helpers ---

def _transition(db: Session, order: Order, target: OrderStatus) -> None:
    if not can_transition(order.status, target):
        raise InvalidStatusTransition(order.status, target)
    old = order.status
    order.status = target
    logger.info(
        "payment_status_changed order_id=%s old_status=%s new_status=%s",
        order.id,
        old.value,
        target.value,
    )


def _get_access(db: Session, order: Order) -> Optional[PurchaseAccess]:
    return (
        db.query(PurchaseAccess)
        .filter(
            PurchaseAccess.user_id == order.user_id,
            PurchaseAccess.experience_id == order.experience_id,
        )
        .first()
    )


def get_user_access(
    db: Session, user_id: int, experience_id: int
) -> Optional[PurchaseAccess]:
    return (
        db.query(PurchaseAccess)
        .filter(
            PurchaseAccess.user_id == user_id,
            PurchaseAccess.experience_id == experience_id,
        )
        .first()
    )
