from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.experience import Experience, ExperiencePoint, ExperienceStatus
from app.models.user import User, UserRole
from app.schemas.author import (
    AuthorExperienceCreate,
    AuthorExperienceListItem,
    AuthorExperienceRead,
    AuthorExperienceUpdate,
)
from app.services.audit import record_internal_event, write_audit_log
from app.services.auth import require_roles

router = APIRouter(prefix="/author", tags=["author"])
logger = logging.getLogger("app.author")

# Поля, обязательные для отправки на модерацию (submit).
REQUIRED_SUBMIT_FIELDS = ("title", "full_description", "city", "duration_minutes", "price")


def _author_only(current_user: User = Depends(require_roles(UserRole.Author))) -> User:
    return current_user


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found")


def _get_own_experience(db: Session, experience_id: int, author: User) -> Experience:
    exp = db.get(Experience, experience_id)
    # Чужой / несуществующий author-experience скрываем через 404.
    if exp is None or exp.author_id != author.id:
        logger.info(
            "author_experience_access_denied author_id=%s experience_id=%s status_code=404",
            author.id,
            experience_id,
        )
        raise _not_found()
    return exp


def _apply_points(db: Session, exp: Experience, points) -> None:
    """Полностью заменить набор точек experience."""
    for p in list(exp.points):
        db.delete(p)
    exp.points.clear()
    db.flush()
    for idx, p in enumerate(points, start=1):
        db.add(
            ExperiencePoint(
                experience_id=exp.id,
                order=p.order if p.order is not None else idx,
                title=p.title,
                description=p.description,
                lat=p.lat,
                lon=p.lon,
            )
        )
    db.flush()


@router.get("/experiences", response_model=List[AuthorExperienceListItem])
def list_author_experiences(
    db: Session = Depends(get_db),
    current_user: User = Depends(_author_only),
) -> List[AuthorExperienceListItem]:
    rows = (
        db.query(Experience)
        .filter(Experience.author_id == current_user.id)
        .order_by(Experience.updated_at.desc(), Experience.id.desc())
        .all()
    )
    logger.info(
        "author_experiences_list author_id=%s count=%s", current_user.id, len(rows)
    )
    return [AuthorExperienceListItem.model_validate(r) for r in rows]


@router.post(
    "/experiences",
    response_model=AuthorExperienceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_author_experience(
    payload: AuthorExperienceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_author_only),
) -> AuthorExperienceRead:
    exp = Experience(
        author_id=current_user.id,
        title=payload.title,
        short_description=payload.short_description,
        full_description=payload.full_description,
        city=payload.city,
        duration_minutes=payload.duration_minutes,
        price=payload.price,
        restrictions=payload.restrictions,
        status=ExperienceStatus.draft,
    )
    db.add(exp)
    db.flush()
    if payload.points:
        _apply_points(db, exp, payload.points)

    write_audit_log(
        db,
        action="author_experience_created",
        target_type="experience",
        target_id=exp.id,
        actor_user_id=current_user.id,
        result="ok",
        metadata={"status": exp.status.value},
    )
    record_internal_event(
        db,
        event_name="author_experience_created",
        user_id=current_user.id,
        entity_type="experience",
        entity_id=exp.id,
    )
    db.commit()
    db.refresh(exp)
    logger.info(
        "author_experience_created author_id=%s experience_id=%s", current_user.id, exp.id
    )
    return AuthorExperienceRead.model_validate(exp)


@router.get("/experiences/{experience_id}", response_model=AuthorExperienceRead)
def get_author_experience(
    experience_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_author_only),
) -> AuthorExperienceRead:
    exp = _get_own_experience(db, experience_id, current_user)
    return AuthorExperienceRead.model_validate(exp)


@router.patch("/experiences/{experience_id}", response_model=AuthorExperienceRead)
def update_author_experience(
    experience_id: int,
    payload: AuthorExperienceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_author_only),
) -> AuthorExperienceRead:
    exp = _get_own_experience(db, experience_id, current_user)

    # PATCH разрешён только для draft/rejected. Author не управляет published напрямую.
    if exp.status not in (ExperienceStatus.draft, ExperienceStatus.rejected):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft or rejected experiences can be edited",
        )

    data = payload.model_dump(exclude_unset=True)
    for field in ("title", "short_description", "full_description", "city",
                  "duration_minutes", "price", "restrictions"):
        if field in data and data[field] is not None:
            setattr(exp, field, data[field])

    if payload.points is not None:
        _apply_points(db, exp, payload.points)

    write_audit_log(
        db,
        action="author_experience_updated",
        target_type="experience",
        target_id=exp.id,
        actor_user_id=current_user.id,
        result="ok",
        metadata={"status": exp.status.value},
    )
    record_internal_event(
        db,
        event_name="author_experience_updated",
        user_id=current_user.id,
        entity_type="experience",
        entity_id=exp.id,
    )
    db.commit()
    db.refresh(exp)
    logger.info(
        "author_experience_updated author_id=%s experience_id=%s", current_user.id, exp.id
    )
    return AuthorExperienceRead.model_validate(exp)


@router.post("/experiences/{experience_id}/submit", response_model=AuthorExperienceRead)
def submit_author_experience(
    experience_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_author_only),
) -> AuthorExperienceRead:
    exp = _get_own_experience(db, experience_id, current_user)

    if exp.status not in (ExperienceStatus.draft, ExperienceStatus.rejected):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft or rejected experiences can be submitted",
        )

    # Валидация минимально нужных полей + наличие точек.
    missing = [f for f in REQUIRED_SUBMIT_FIELDS if getattr(exp, f) in (None, "")]
    if not exp.points:
        missing.append("points")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required fields for submit: {', '.join(missing)}",
        )

    # После повторного submit отклонённое впечатление снова идёт на модерацию,
    # причина прошлого отклонения очищается.
    exp.status = ExperienceStatus.on_moderation
    exp.moderation_reason_code = None
    exp.moderation_reason_text = None

    write_audit_log(
        db,
        action="author_experience_submitted",
        target_type="experience",
        target_id=exp.id,
        actor_user_id=current_user.id,
        result="ok",
        metadata={"status": exp.status.value},
    )
    record_internal_event(
        db,
        event_name="author_experience_submitted",
        user_id=current_user.id,
        entity_type="experience",
        entity_id=exp.id,
    )
    db.commit()
    db.refresh(exp)
    logger.info(
        "author_experience_submitted author_id=%s experience_id=%s", current_user.id, exp.id
    )
    return AuthorExperienceRead.model_validate(exp)
