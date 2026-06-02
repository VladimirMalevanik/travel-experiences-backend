from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.experience import Experience
from app.models.order import PurchaseAccess
from app.models.user import User, UserRole
from app.schemas.order import PurchaseAccessRead
from app.services.auth import require_roles
from app.services.payments import get_user_access

router = APIRouter(prefix="/purchases", tags=["purchases"])
logger = logging.getLogger("app.purchases")


def _user_only(current_user: User = Depends(require_roles(UserRole.User))) -> User:
    return current_user


@router.get(
    "/experiences/{experience_id}/access",
    response_model=PurchaseAccessRead,
)
def check_access(
    experience_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> PurchaseAccessRead:
    experience = db.get(Experience, experience_id)
    if experience is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )

    access: PurchaseAccess | None = get_user_access(db, current_user.id, experience_id)
    access_granted = access is not None

    logger.info(
        "access_checked user_id=%s experience_id=%s access_granted=%s",
        current_user.id,
        experience_id,
        access_granted,
    )

    if access is None:
        return PurchaseAccessRead(
            experience_id=experience_id,
            access_granted=False,
            order_id=None,
            granted_at=None,
        )
    return PurchaseAccessRead(
        experience_id=experience_id,
        access_granted=True,
        order_id=access.order_id,
        granted_at=access.granted_at,
    )
