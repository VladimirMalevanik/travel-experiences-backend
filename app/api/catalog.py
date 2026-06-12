from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.experience import Experience, ExperienceStatus
from app.models.user import User
from app.schemas.experience import (
    CatalogConfigRead,
    ExperienceListItem,
    ExperienceListResponse,
)
from app.services.auth import get_current_user

router = APIRouter(tags=["catalog"])
logger = logging.getLogger("app.catalog")

MAX_PAGE_SIZE = 50
DEFAULT_SORT = ["city:asc", "duration_minutes:asc", "id:asc"]
CATALOG_VERSION = 1
# Окно длительности витрины по ТЗ: 2–6 часов.
SHOWCASE_TIME_WINDOW_HOURS = [2, 6]
PRIORITY_RULES = [
    "status:published",
    "city:asc",
    "duration_minutes:asc",
    "id:asc",
]
SUPPORTED_FILTERS = [
    "city",
    "min_duration_minutes",
    "max_duration_minutes",
    "time_window_hours",
    "min_price",
    "max_price",
]


@router.get("/catalog/experiences", response_model=ExperienceListResponse)
def list_catalog(
    city: Optional[str] = Query(default=None),
    min_duration_minutes: Optional[int] = Query(default=None, ge=0),
    max_duration_minutes: Optional[int] = Query(default=None, ge=0),
    time_window_hours: Optional[int] = Query(default=None, ge=0),
    min_price: Optional[float] = Query(default=None, ge=0),
    max_price: Optional[float] = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExperienceListResponse:
    # time_window_hours задаёт верхнюю границу длительности в минутах.
    # Не ломает старые min/max_duration_minutes — комбинируется как доп. фильтр.
    if time_window_hours is not None:
        window_max = time_window_hours * 60
        if max_duration_minutes is None or window_max < max_duration_minutes:
            max_duration_minutes = window_max

    if (
        min_duration_minutes is not None
        and max_duration_minutes is not None
        and min_duration_minutes > max_duration_minutes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_duration_minutes must be <= max_duration_minutes",
        )
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_price must be <= max_price",
        )

    query = db.query(Experience).filter(Experience.status == ExperienceStatus.published)

    if city is not None:
        query = query.filter(Experience.city == city)
    if min_duration_minutes is not None:
        query = query.filter(Experience.duration_minutes >= min_duration_minutes)
    if max_duration_minutes is not None:
        query = query.filter(Experience.duration_minutes <= max_duration_minutes)
    if min_price is not None:
        query = query.filter(Experience.price >= min_price)
    if max_price is not None:
        query = query.filter(Experience.price <= max_price)

    total = query.count()

    rows = (
        query.order_by(
            Experience.city.asc(),
            Experience.duration_minutes.asc(),
            Experience.id.asc(),
        )
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = [ExperienceListItem.model_validate(r) for r in rows]

    logger.info(
        "catalog list user_id=%s city=%s min_dur=%s max_dur=%s min_price=%s max_price=%s "
        "page=%s size=%s total=%s returned=%s",
        current_user.id,
        city,
        min_duration_minutes,
        max_duration_minutes,
        min_price,
        max_price,
        page,
        size,
        total,
        len(items),
    )

    return ExperienceListResponse(items=items, page=page, size=size, total=total)


@router.get("/catalog/config", response_model=CatalogConfigRead)
def catalog_config(
    current_user: User = Depends(get_current_user),
) -> CatalogConfigRead:
    logger.info("catalog config requested user_id=%s", current_user.id)
    return CatalogConfigRead(
        default_sort=DEFAULT_SORT,
        max_page_size=MAX_PAGE_SIZE,
        source="server_config",
        priority_rules=PRIORITY_RULES,
        showcase_priorities=PRIORITY_RULES,
        supported_filters=SUPPORTED_FILTERS,
        version=CATALOG_VERSION,
        time_window_hours=SHOWCASE_TIME_WINDOW_HOURS,
    )
