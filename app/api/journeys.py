from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.experience import Experience, ExperiencePoint
from app.models.journey import Journey, JourneyProgress, JourneyStatus, JourneyType
from app.models.order import PurchaseAccess
from app.models.route import PersonalRoute, RoutePoint
from app.models.user import User, UserRole
from app.schemas.journey import (
    JourneyProgressPointRead,
    JourneyRead,
    RouteJourneyProgressRequest,
)
from app.services.auth import require_roles
from app.services.payments import get_user_access

router = APIRouter(prefix="/journeys", tags=["journeys"])
logger = logging.getLogger("app.journeys")


def _user_only(current_user: User = Depends(require_roles(UserRole.User))) -> User:
    return current_user


def _get_own_route(db: Session, route_id: int, user_id: int) -> PersonalRoute:
    route = (
        db.query(PersonalRoute)
        .filter(PersonalRoute.id == route_id, PersonalRoute.owner_id == user_id)
        .first()
    )
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    return route


def _get_started_journey(db: Session, user_id: int, route_id: int) -> Journey | None:
    return (
        db.query(Journey)
        .filter(
            Journey.user_id == user_id,
            Journey.journey_type == JourneyType.route,
            Journey.target_id == route_id,
            Journey.status == JourneyStatus.started,
        )
        .order_by(Journey.id.desc())
        .first()
    )


def _journey_detail(db: Session, journey: Journey) -> JourneyRead:
    progress_rows = (
        db.query(JourneyProgress)
        .filter(JourneyProgress.journey_id == journey.id)
        .order_by(JourneyProgress.completed_at.asc(), JourneyProgress.id.asc())
        .all()
    )
    completed = [
        JourneyProgressPointRead(point_id=p.point_id, completed_at=p.completed_at)
        for p in progress_rows
    ]
    return JourneyRead(
        id=journey.id,
        journey_type=journey.journey_type,
        target_id=journey.target_id,
        status=journey.status,
        started_at=journey.started_at,
        updated_at=journey.updated_at,
        finished_at=journey.finished_at,
        completed_points=completed,
    )


@router.post("/route/{route_id}/start", response_model=JourneyRead)
def start_route_journey(
    route_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> JourneyRead:
    route = _get_own_route(db, route_id, current_user.id)
    points_count = (
        db.query(RoutePoint).filter(RoutePoint.route_id == route.id).count()
    )
    if points_count < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Route must have at least one point",
        )

    existing = _get_started_journey(db, current_user.id, route.id)
    if existing is not None:
        return _journey_detail(db, existing)

    journey = Journey(
        user_id=current_user.id,
        journey_type=JourneyType.route,
        target_id=route.id,
        status=JourneyStatus.started,
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)
    logger.info(
        "route_journey_started user_id=%s route_id=%s journey_id=%s",
        current_user.id,
        route.id,
        journey.id,
    )
    return _journey_detail(db, journey)


@router.post("/route/{route_id}/progress", response_model=JourneyRead)
def progress_route_journey(
    route_id: int,
    payload: RouteJourneyProgressRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> JourneyRead:
    route = _get_own_route(db, route_id, current_user.id)
    journey = _get_started_journey(db, current_user.id, route.id)
    if journey is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No started journey for this route",
        )
    point = (
        db.query(RoutePoint)
        .filter(RoutePoint.id == payload.point_id, RoutePoint.route_id == route.id)
        .first()
    )
    if point is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Point not found")

    existing_progress = (
        db.query(JourneyProgress)
        .filter(
            JourneyProgress.journey_id == journey.id,
            JourneyProgress.point_id == point.id,
        )
        .first()
    )
    if existing_progress is None:
        db.add(JourneyProgress(journey_id=journey.id, point_id=point.id))
        journey.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(journey)
        logger.info(
            "route_journey_progress user_id=%s route_id=%s journey_id=%s point_id=%s",
            current_user.id,
            route.id,
            journey.id,
            point.id,
        )
    return _journey_detail(db, journey)


@router.post("/route/{route_id}/complete", response_model=JourneyRead)
def complete_route_journey(
    route_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> JourneyRead:
    route = _get_own_route(db, route_id, current_user.id)
    journey = _get_started_journey(db, current_user.id, route.id)
    if journey is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No started journey for this route",
        )
    now = datetime.now(timezone.utc)
    journey.status = JourneyStatus.completed
    journey.finished_at = now
    journey.updated_at = now
    db.commit()
    db.refresh(journey)
    logger.info(
        "route_journey_completed user_id=%s route_id=%s journey_id=%s",
        current_user.id,
        route.id,
        journey.id,
    )
    return _journey_detail(db, journey)


# --- Experience journeys (FR-08 for purchased experiences) ---


def _require_experience_with_access(
    db: Session, experience_id: int, current_user: User
) -> Experience:
    experience = db.get(Experience, experience_id)
    if experience is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experience not found"
        )
    access: PurchaseAccess | None = get_user_access(db, current_user.id, experience_id)
    if access is None:
        logger.info(
            "experience_journey_access_denied user_id=%s experience_id=%s",
            current_user.id,
            experience_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No purchase access for this experience",
        )
    return experience


def _get_started_experience_journey(
    db: Session, user_id: int, experience_id: int
) -> Journey | None:
    return (
        db.query(Journey)
        .filter(
            Journey.user_id == user_id,
            Journey.journey_type == JourneyType.experience,
            Journey.target_id == experience_id,
            Journey.status == JourneyStatus.started,
        )
        .order_by(Journey.id.desc())
        .first()
    )


@router.post("/experience/{experience_id}/start", response_model=JourneyRead)
def start_experience_journey(
    experience_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> JourneyRead:
    experience = _require_experience_with_access(db, experience_id, current_user)

    points_count = (
        db.query(ExperiencePoint)
        .filter(ExperiencePoint.experience_id == experience.id)
        .count()
    )
    if points_count < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Experience must have at least one point",
        )

    existing = _get_started_experience_journey(db, current_user.id, experience.id)
    if existing is not None:
        return _journey_detail(db, existing)

    journey = Journey(
        user_id=current_user.id,
        journey_type=JourneyType.experience,
        target_id=experience.id,
        status=JourneyStatus.started,
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)
    logger.info(
        "experience_journey_started user_id=%s experience_id=%s journey_id=%s",
        current_user.id,
        experience.id,
        journey.id,
    )
    return _journey_detail(db, journey)


@router.post("/experience/{experience_id}/progress", response_model=JourneyRead)
def progress_experience_journey(
    experience_id: int,
    payload: RouteJourneyProgressRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> JourneyRead:
    experience = _require_experience_with_access(db, experience_id, current_user)
    journey = _get_started_experience_journey(db, current_user.id, experience.id)
    if journey is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No started journey for this experience",
        )
    point = (
        db.query(ExperiencePoint)
        .filter(
            ExperiencePoint.id == payload.point_id,
            ExperiencePoint.experience_id == experience.id,
        )
        .first()
    )
    if point is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Point not found"
        )

    existing_progress = (
        db.query(JourneyProgress)
        .filter(
            JourneyProgress.journey_id == journey.id,
            JourneyProgress.point_id == point.id,
        )
        .first()
    )
    if existing_progress is None:
        db.add(JourneyProgress(journey_id=journey.id, point_id=point.id))
        journey.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(journey)
        logger.info(
            "experience_journey_progress user_id=%s experience_id=%s journey_id=%s point_id=%s",
            current_user.id,
            experience.id,
            journey.id,
            point.id,
        )
    return _journey_detail(db, journey)


@router.post("/experience/{experience_id}/complete", response_model=JourneyRead)
def complete_experience_journey(
    experience_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> JourneyRead:
    experience = _require_experience_with_access(db, experience_id, current_user)
    journey = _get_started_experience_journey(db, current_user.id, experience.id)
    if journey is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No started journey for this experience",
        )
    now = datetime.now(timezone.utc)
    journey.status = JourneyStatus.completed
    journey.finished_at = now
    journey.updated_at = now
    db.commit()
    db.refresh(journey)
    logger.info(
        "experience_journey_completed user_id=%s experience_id=%s journey_id=%s",
        current_user.id,
        experience.id,
        journey.id,
    )
    return _journey_detail(db, journey)
