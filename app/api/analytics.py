from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.analytics import AnalyticsEvent
from app.models.user import User, UserRole
from app.schemas.analytics import (
    AnalyticsBasicReport,
    AnalyticsEventIn,
    AnalyticsEventsAccepted,
)
from app.services.auth import get_current_user, require_roles

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger("app.analytics")


def _parse_events(body: Dict[str, Any]) -> List[AnalyticsEventIn]:
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Body must be an object",
        )
    try:
        if "events" in body:
            raw_list = body.get("events")
            if not isinstance(raw_list, list) or not raw_list:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="events must be a non-empty list",
                )
            return [AnalyticsEventIn.model_validate(item) for item in raw_list]
        return [AnalyticsEventIn.model_validate(body)]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
        ) from exc


@router.post("/events", response_model=AnalyticsEventsAccepted)
def ingest_events(
    body: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyticsEventsAccepted:
    events = _parse_events(body)
    rows: List[AnalyticsEvent] = []
    for evt in events:
        rows.append(
            AnalyticsEvent(
                event_name=evt.event_name,
                user_id=current_user.id,
                session_id=evt.session_id,
                source_app=evt.source_app,
                entity_type=evt.entity_type,
                entity_id=evt.entity_id,
                payload=json.dumps(evt.payload, ensure_ascii=False)
                if evt.payload is not None
                else None,
            )
        )
    db.add_all(rows)
    db.commit()
    accepted = len(rows)
    logger.info(
        "analytics_events_accepted user_id=%s accepted_count=%s",
        current_user.id,
        accepted,
    )
    return AnalyticsEventsAccepted(accepted=accepted)


@router.get("/reports/basic", response_model=AnalyticsBasicReport)
def basic_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.Moderator)),
) -> AnalyticsBasicReport:
    total = db.query(func.count(AnalyticsEvent.id)).scalar() or 0
    by_name_rows = (
        db.query(AnalyticsEvent.event_name, func.count(AnalyticsEvent.id))
        .group_by(AnalyticsEvent.event_name)
        .all()
    )
    events_by_name = {name: int(count) for name, count in by_name_rows}
    logger.info(
        "analytics_report_opened user_id=%s total_events=%s",
        current_user.id,
        int(total),
    )
    return AnalyticsBasicReport(total_events=int(total), events_by_name=events_by_name)
