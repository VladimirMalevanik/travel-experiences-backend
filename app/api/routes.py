from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.route import PersonalRoute, RoutePoint, RouteStatus
from app.models.user import User, UserRole
from app.schemas.route import (
    PersonalRouteCreate,
    PersonalRouteListItem,
    PersonalRouteRead,
    PersonalRouteUpdate,
    RoutePointCreate,
    RoutePointRead,
    RoutePointUpdate,
    RouteReorderRequest,
)
from app.services.auth import require_roles

router = APIRouter(prefix="/me/routes", tags=["routes"])
logger = logging.getLogger("app.routes")

MAX_POINTS_PER_ROUTE = 30


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


def _touch_route(route: PersonalRoute) -> None:
    route.updated_at = datetime.now(timezone.utc)


def _route_detail(route: PersonalRoute) -> PersonalRouteRead:
    points = sorted(route.points, key=lambda p: p.order)
    return PersonalRouteRead(
        id=route.id,
        name=route.name,
        status=route.status,
        points=[RoutePointRead.model_validate(p) for p in points],
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


@router.get("", response_model=List[PersonalRouteListItem])
def list_routes(
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> List[PersonalRouteListItem]:
    rows = (
        db.query(
            PersonalRoute,
            func.count(RoutePoint.id).label("points_count"),
        )
        .outerjoin(RoutePoint, RoutePoint.route_id == PersonalRoute.id)
        .filter(PersonalRoute.owner_id == current_user.id)
        .group_by(PersonalRoute.id)
        .order_by(PersonalRoute.updated_at.desc(), PersonalRoute.id.desc())
        .all()
    )
    return [
        PersonalRouteListItem(
            id=r.id,
            name=r.name,
            status=r.status,
            points_count=int(cnt or 0),
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r, cnt in rows
    ]


@router.post("", response_model=PersonalRouteRead, status_code=status.HTTP_201_CREATED)
def create_route(
    payload: PersonalRouteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> PersonalRouteRead:
    route = PersonalRoute(
        owner_id=current_user.id,
        name=payload.name,
        status=RouteStatus.draft,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    logger.info("route_created user_id=%s route_id=%s", current_user.id, route.id)
    return _route_detail(route)


@router.get("/{route_id}", response_model=PersonalRouteRead)
def get_route(
    route_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> PersonalRouteRead:
    route = _get_own_route(db, route_id, current_user.id)
    return _route_detail(route)


@router.patch("/{route_id}", response_model=PersonalRouteRead)
def update_route(
    route_id: int,
    payload: PersonalRouteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> PersonalRouteRead:
    route = _get_own_route(db, route_id, current_user.id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        route.name = data["name"]
    if "status" in data and data["status"] is not None:
        route.status = data["status"]
    _touch_route(route)
    db.commit()
    db.refresh(route)
    logger.info("route_updated user_id=%s route_id=%s", current_user.id, route.id)
    return _route_detail(route)


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(
    route_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> Response:
    route = _get_own_route(db, route_id, current_user.id)
    db.delete(route)
    db.commit()
    logger.info("route_deleted user_id=%s route_id=%s", current_user.id, route_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{route_id}/points",
    response_model=RoutePointRead,
    status_code=status.HTTP_201_CREATED,
)
def add_point(
    route_id: int,
    payload: RoutePointCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> RoutePointRead:
    route = _get_own_route(db, route_id, current_user.id)
    existing_count = (
        db.query(func.count(RoutePoint.id)).filter(RoutePoint.route_id == route.id).scalar() or 0
    )
    if existing_count >= MAX_POINTS_PER_ROUTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Max {MAX_POINTS_PER_ROUTE} points per route",
        )

    if payload.order is None:
        max_order = (
            db.query(func.max(RoutePoint.order))
            .filter(RoutePoint.route_id == route.id)
            .scalar()
        )
        order = (max_order or 0) + 1
    else:
        order = payload.order

    point = RoutePoint(
        route_id=route.id,
        order=order,
        title=payload.title,
        note=payload.note,
        lat=payload.lat,
        lon=payload.lon,
    )
    db.add(point)
    _touch_route(route)
    db.commit()
    db.refresh(point)
    logger.info(
        "route_point_added user_id=%s route_id=%s point_id=%s",
        current_user.id,
        route.id,
        point.id,
    )
    return RoutePointRead.model_validate(point)


@router.patch(
    "/{route_id}/points/{point_id}",
    response_model=RoutePointRead,
)
def update_point(
    route_id: int,
    point_id: int,
    payload: RoutePointUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> RoutePointRead:
    route = _get_own_route(db, route_id, current_user.id)
    point = (
        db.query(RoutePoint)
        .filter(RoutePoint.id == point_id, RoutePoint.route_id == route.id)
        .first()
    )
    if point is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Point not found")
    data = payload.model_dump(exclude_unset=True)
    for field in ("title", "note", "lat", "lon", "order"):
        if field in data:
            setattr(point, field, data[field])
    _touch_route(route)
    db.commit()
    db.refresh(point)
    logger.info(
        "route_point_updated user_id=%s route_id=%s point_id=%s",
        current_user.id,
        route.id,
        point.id,
    )
    return RoutePointRead.model_validate(point)


@router.delete(
    "/{route_id}/points/{point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_point(
    route_id: int,
    point_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> Response:
    route = _get_own_route(db, route_id, current_user.id)
    point = (
        db.query(RoutePoint)
        .filter(RoutePoint.id == point_id, RoutePoint.route_id == route.id)
        .first()
    )
    if point is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Point not found")
    db.delete(point)
    _touch_route(route)
    db.commit()
    logger.info(
        "route_point_deleted user_id=%s route_id=%s point_id=%s",
        current_user.id,
        route.id,
        point_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{route_id}/reorder", response_model=PersonalRouteRead)
def reorder_points(
    route_id: int,
    payload: RouteReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_only),
) -> PersonalRouteRead:
    route = _get_own_route(db, route_id, current_user.id)
    points = db.query(RoutePoint).filter(RoutePoint.route_id == route.id).all()
    existing_ids = {p.id for p in points}
    requested = payload.point_ids
    if (
        len(requested) != len(existing_ids)
        or len(set(requested)) != len(requested)
        or set(requested) != existing_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="point_ids must contain exactly all existing point ids without duplicates",
        )

    by_id = {p.id: p for p in points}
    for new_order, pid in enumerate(requested, start=1):
        by_id[pid].order = new_order
    _touch_route(route)
    db.commit()
    db.refresh(route)
    logger.info(
        "route_reordered user_id=%s route_id=%s point_count=%s",
        current_user.id,
        route.id,
        len(requested),
    )
    return _route_detail(route)
