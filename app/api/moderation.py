from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.complaint import Complaint, ComplaintStatus
from app.models.experience import Experience, ExperienceStatus
from app.models.moderation import ModerationDecision, ModerationDecisionType
from app.models.user import User, UserRole
from app.schemas.complaint import (
    ComplaintListResponse,
    ComplaintRead,
    ComplaintResolveRequest,
)
from app.schemas.moderation import (
    ModerationQueueResponse,
    ModerationRejectRequest,
    ModerationResultRead,
)
from app.services.audit import record_internal_event, write_audit_log
from app.services.auth import require_roles

router = APIRouter(prefix="/moderation", tags=["moderation"])
logger = logging.getLogger("app.moderation")


def _moderator_only(current_user: User = Depends(require_roles(UserRole.Moderator))) -> User:
    return current_user


@router.get("/queue", response_model=ModerationQueueResponse)
def moderation_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(_moderator_only),
) -> ModerationQueueResponse:
    rows = (
        db.query(Experience)
        .filter(Experience.status == ExperienceStatus.on_moderation)
        .order_by(Experience.updated_at.asc(), Experience.id.asc())
        .all()
    )
    logger.info("moderation_queue moderator_id=%s count=%s", current_user.id, len(rows))
    return ModerationQueueResponse(items=rows, total=len(rows))


@router.post("/experiences/{experience_id}/publish", response_model=ModerationResultRead)
def publish_experience(
    experience_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_moderator_only),
) -> ModerationResultRead:
    exp = db.get(Experience, experience_id)
    if exp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )
    if exp.status != ExperienceStatus.on_moderation:
        write_audit_log(
            db,
            action="moderation_publish",
            target_type="experience",
            target_id=exp.id,
            actor_user_id=current_user.id,
            result="invalid",
            reason="experience is not on_moderation",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only experiences on moderation can be published",
        )

    exp.status = ExperienceStatus.published
    exp.moderation_reason_code = None
    exp.moderation_reason_text = None
    db.add(
        ModerationDecision(
            experience_id=exp.id,
            moderator_id=current_user.id,
            decision=ModerationDecisionType.publish,
        )
    )
    write_audit_log(
        db,
        action="moderation_publish",
        target_type="experience",
        target_id=exp.id,
        actor_user_id=current_user.id,
        result="ok",
    )
    record_internal_event(
        db,
        event_name="moderation_publish",
        user_id=current_user.id,
        entity_type="experience",
        entity_id=exp.id,
    )
    db.commit()
    db.refresh(exp)
    logger.info(
        "moderation_publish moderator_id=%s experience_id=%s", current_user.id, exp.id
    )
    return ModerationResultRead.model_validate(exp)


@router.post("/experiences/{experience_id}/reject", response_model=ModerationResultRead)
def reject_experience(
    experience_id: int,
    payload: ModerationRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_moderator_only),
) -> ModerationResultRead:
    exp = db.get(Experience, experience_id)
    if exp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )
    if exp.status != ExperienceStatus.on_moderation:
        write_audit_log(
            db,
            action="moderation_reject",
            target_type="experience",
            target_id=exp.id,
            actor_user_id=current_user.id,
            result="invalid",
            reason="experience is not on_moderation",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only experiences on moderation can be rejected",
        )

    exp.status = ExperienceStatus.rejected
    exp.moderation_reason_code = payload.reason_code
    exp.moderation_reason_text = payload.reason_text
    db.add(
        ModerationDecision(
            experience_id=exp.id,
            moderator_id=current_user.id,
            decision=ModerationDecisionType.reject,
            reason_code=payload.reason_code,
            reason_text=payload.reason_text,
        )
    )
    write_audit_log(
        db,
        action="moderation_reject",
        target_type="experience",
        target_id=exp.id,
        actor_user_id=current_user.id,
        result="ok",
        reason=payload.reason_code,
    )
    record_internal_event(
        db,
        event_name="moderation_reject",
        user_id=current_user.id,
        entity_type="experience",
        entity_id=exp.id,
        payload={"reason_code": payload.reason_code},
    )
    db.commit()
    db.refresh(exp)
    logger.info(
        "moderation_reject moderator_id=%s experience_id=%s reason_code=%s",
        current_user.id,
        exp.id,
        payload.reason_code,
    )
    return ModerationResultRead.model_validate(exp)


# ---------- complaints (moderation side) ----------


@router.get("/complaints", response_model=ComplaintListResponse)
def list_complaints(
    db: Session = Depends(get_db),
    current_user: User = Depends(_moderator_only),
) -> ComplaintListResponse:
    rows = (
        db.query(Complaint)
        .order_by(Complaint.created_at.desc(), Complaint.id.desc())
        .all()
    )
    logger.info(
        "moderation_complaints_list moderator_id=%s count=%s", current_user.id, len(rows)
    )
    return ComplaintListResponse(items=rows, total=len(rows))


@router.post("/complaints/{complaint_id}/resolve", response_model=ComplaintRead)
def resolve_complaint(
    complaint_id: int,
    payload: ComplaintResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_moderator_only),
) -> ComplaintRead:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found"
        )
    if complaint.status != ComplaintStatus.open:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complaint is already closed",
        )

    complaint.status = payload.status
    complaint.resolution_text = payload.resolution_text or payload.reason_text
    complaint.moderator_id = current_user.id
    complaint.resolved_at = datetime.now(timezone.utc)

    write_audit_log(
        db,
        action="complaint_resolved",
        target_type="complaint",
        target_id=complaint.id,
        actor_user_id=current_user.id,
        result="ok",
        reason=complaint.status.value,
    )
    record_internal_event(
        db,
        event_name="complaint_resolved",
        user_id=current_user.id,
        entity_type="complaint",
        entity_id=complaint.id,
        payload={"status": complaint.status.value},
    )
    db.commit()
    db.refresh(complaint)
    logger.info(
        "complaint_resolved moderator_id=%s complaint_id=%s status=%s",
        current_user.id,
        complaint.id,
        complaint.status.value,
    )
    return ComplaintRead.model_validate(complaint)
