from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.journey import Journey, JourneyStatus, JourneyType
from app.models.review import Review, ReviewTargetType
from app.models.user import User, UserRole
from app.schemas.review import ReviewCreate, ReviewRead
from app.services.auth import require_roles

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = logging.getLogger("app.reviews")


def _user_only(current_user: User = Depends(require_roles(UserRole.User))) -> User:
    return current_user


def _reject(user_id: int, reason: str) -> None:
    logger.info("review_rejected_validation user_id=%s reason=%s", user_id, reason)


@router.post("", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
def create_review(
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> ReviewRead:
    journey = db.get(Journey, payload.journey_id)
    if journey is None or journey.user_id != current_user.id:
        _reject(current_user.id, "journey_not_found_or_foreign")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Journey not found"
        )

    if journey.status != JourneyStatus.completed:
        _reject(current_user.id, "journey_not_completed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Journey must be completed before review",
        )

    expected_type = (
        JourneyType.experience
        if payload.target_type == ReviewTargetType.experience
        else JourneyType.route
    )
    if journey.journey_type != expected_type or journey.target_id != payload.target_id:
        _reject(current_user.id, "target_mismatch")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Journey target does not match review target",
        )

    duplicate = (
        db.query(Review)
        .filter(
            Review.journey_id == journey.id,
            Review.user_id == current_user.id,
        )
        .first()
    )
    if duplicate is not None:
        _reject(current_user.id, "duplicate_review")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review for this journey already exists",
        )

    review = Review(
        user_id=current_user.id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        journey_id=journey.id,
        rating=payload.rating,
        text=payload.text,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    logger.info(
        "review_submitted user_id=%s review_id=%s target_type=%s target_id=%s journey_id=%s",
        current_user.id,
        review.id,
        review.target_type.value,
        review.target_id,
        review.journey_id,
    )
    return ReviewRead.model_validate(review)
