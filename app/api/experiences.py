from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.experience import Experience, ExperienceStatus
from app.models.user import User, UserRole
from app.schemas.experience import ExperiencePointRead, ExperienceRead
from app.services.auth import get_current_user

router = APIRouter(tags=["experiences"])
logger = logging.getLogger("app.experiences")


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found")


@router.get("/experiences/{experience_id}", response_model=ExperienceRead)
def get_experience(
    experience_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExperienceRead:
    experience = db.get(Experience, experience_id)
    if experience is None:
        logger.info(
            "experience card miss user_id=%s experience_id=%s status_code=404",
            current_user.id,
            experience_id,
        )
        raise _not_found()

    is_published = experience.status == ExperienceStatus.published

    if not is_published:
        is_moderator = current_user.role == UserRole.Moderator
        is_owner_author = (
            current_user.role == UserRole.Author
            and experience.author_id == current_user.id
        )
        if not (is_moderator or is_owner_author):
            logger.info(
                "experience card hidden user_id=%s role=%s experience_id=%s "
                "experience_status=%s status_code=404",
                current_user.id,
                current_user.role.value,
                experience_id,
                experience.status.value,
            )
            raise _not_found()

    points_sorted = sorted(experience.points, key=lambda p: p.order)
    points = [ExperiencePointRead.model_validate(p) for p in points_sorted]

    response = ExperienceRead(
        id=experience.id,
        title=experience.title,
        short_description=experience.short_description,
        full_description=experience.full_description,
        city=experience.city,
        duration_minutes=experience.duration_minutes,
        price=experience.price,
        restrictions=experience.restrictions,
        status=experience.status,
        purchase_available=is_published,
        points=points,
    )

    logger.info(
        "experience card view user_id=%s role=%s experience_id=%s "
        "experience_status=%s purchase_available=%s status_code=200",
        current_user.id,
        current_user.role.value,
        experience.id,
        experience.status.value,
        is_published,
    )

    return response
