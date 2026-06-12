"""Helper для записи аудита и внутренних аналитических событий (FR-13, FR-14, NFR-06).

В аудит и аналитику не пишутся JWT, пароли и чувствительные пользовательские
заметки — только идентификаторы, статусы и безопасные метаданные.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.analytics import AnalyticsEvent
from app.models.audit import AuditLog


def write_audit_log(
    db: Session,
    *,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    result: str = "ok",
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Записать запись аудита. Не коммитит — коммит на стороне вызывающего."""
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        result=result,
        reason=reason,
        metadata_json=json.dumps(metadata, ensure_ascii=False)
        if metadata is not None
        else None,
    )
    db.add(entry)
    return entry


def record_internal_event(
    db: Session,
    *,
    event_name: str,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> AnalyticsEvent:
    """Зафиксировать внутреннее backend-событие как AnalyticsEvent.

    Не коммитит — коммит на стороне вызывающего.
    """
    event = AnalyticsEvent(
        event_name=event_name,
        user_id=user_id,
        session_id=None,
        source_app="backend",
        entity_type=entity_type,
        entity_id=entity_id,
        event_version=1,
        occurred_at=datetime.now(timezone.utc),
        payload=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
    )
    db.add(event)
    return event
