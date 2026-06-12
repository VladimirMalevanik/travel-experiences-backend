from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.complaint import Complaint, ComplaintStatus
from app.models.experience import Experience
from app.models.user import User, UserRole
from app.schemas.complaint import ComplaintCreate, ComplaintRead
from app.services.audit import record_internal_event, write_audit_log
from app.services.auth import require_roles

router = APIRouter(prefix="/complaints", tags=["complaints"])
logger = logging.getLogger("app.complaints")


def _user_only(current_user: User = Depends(require_roles(UserRole.User))) -> User:
    return current_user


@router.post("", response_model=ComplaintRead, status_code=status.HTTP_201_CREATED)
def create_complaint(
    payload: ComplaintCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> ComplaintRead:
    # Для MVP поддерживается жалоба на experience.
    if payload.target_type == "experience":
        target = db.get(Experience, payload.target_id)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target experience not found",
            )

    complaint = Complaint(
        reporter_user_id=current_user.id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
        status=ComplaintStatus.open,
    )
    db.add(complaint)
    db.flush()

    write_audit_log(
        db,
        action="complaint_created",
        target_type="complaint",
        target_id=complaint.id,
        actor_user_id=current_user.id,
        result="ok",
        metadata={
            "target_type": payload.target_type,
            "target_id": payload.target_id,
            "reason_code": payload.reason_code,
        },
    )
    record_internal_event(
        db,
        event_name="complaint_created",
        user_id=current_user.id,
        entity_type="complaint",
        entity_id=complaint.id,
        payload={"target_type": payload.target_type, "target_id": payload.target_id},
    )
    db.commit()
    db.refresh(complaint)
    logger.info(
        "complaint_created user_id=%s complaint_id=%s target_type=%s target_id=%s",
        current_user.id,
        complaint.id,
        payload.target_type,
        payload.target_id,
    )
    return ComplaintRead.model_validate(complaint)
