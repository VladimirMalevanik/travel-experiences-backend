from __future__ import annotations

import uuid

import pytest

WEBHOOK_SECRET = "dev-mock-secret"


# ---------- helpers ----------


def _login(client, email: str, password: str = "password") -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def user_token(client) -> str:
    return _login(client, "user@test.com")


@pytest.fixture()
def author_token(client) -> str:
    return _login(client, "author@test.com")


@pytest.fixture()
def moderator_token(client) -> str:
    return _login(client, "moderator@test.com")


def _create_published_experience_with_points(title_hint: str = "exp") -> int:
    from app.db import session as db_session
    from app.models.experience import (
        Experience,
        ExperiencePoint,
        ExperienceStatus,
    )
    from app.models.user import User, UserRole

    db = db_session.SessionLocal()
    try:
        author = db.query(User).filter(User.role == UserRole.Author).first()
        assert author is not None
        exp = Experience(
            author_id=author.id,
            title=f"exp-{title_hint}-{uuid.uuid4().hex[:8]}",
            short_description="t",
            full_description="t",
            city=f"City-{uuid.uuid4().hex[:6]}",
            duration_minutes=60,
            price=100.0,
            status=ExperienceStatus.published,
        )
        db.add(exp)
        db.flush()
        for i in range(2):
            db.add(
                ExperiencePoint(
                    experience_id=exp.id, order=i + 1, title=f"P{i}", description="d"
                )
            )
        db.commit()
        db.refresh(exp)
        return exp.id
    finally:
        db.close()


def _create_published_experience_no_points(title_hint: str = "exp-np") -> int:
    from app.db import session as db_session
    from app.models.experience import Experience, ExperienceStatus
    from app.models.user import User, UserRole

    db = db_session.SessionLocal()
    try:
        author = db.query(User).filter(User.role == UserRole.Author).first()
        exp = Experience(
            author_id=author.id,
            title=f"exp-{title_hint}-{uuid.uuid4().hex[:8]}",
            short_description="t",
            full_description="t",
            city=f"City-{uuid.uuid4().hex[:6]}",
            duration_minutes=10,
            price=10.0,
            status=ExperienceStatus.published,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        return exp.id
    finally:
        db.close()


def _get_experience_points(experience_id: int) -> list[int]:
    from app.db import session as db_session
    from app.models.experience import ExperiencePoint

    db = db_session.SessionLocal()
    try:
        return [
            p.id
            for p in db.query(ExperiencePoint)
            .filter(ExperiencePoint.experience_id == experience_id)
            .order_by(ExperiencePoint.order.asc())
            .all()
        ]
    finally:
        db.close()


def _buy_access(client, token: str, experience_id: int) -> int:
    order = client.post(
        "/orders", json={"experience_id": experience_id}, headers=_h(token)
    )
    assert order.status_code in (200, 201), order.text
    oid = order.json()["id"]
    init = client.post(f"/payments/{oid}/init", headers=_h(token))
    assert init.status_code == 200, init.text
    wh = client.post(
        "/payments/webhook",
        json={
            "order_id": oid,
            "provider_event_id": f"evt_{oid}_{uuid.uuid4().hex[:6]}",
            "status": "paid",
        },
        headers={"X-Mock-Payment-Secret": WEBHOOK_SECRET},
    )
    assert wh.status_code == 200, wh.text
    return oid


def _create_second_user(client) -> str:
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.user import User, UserRole, UserStatus

    email = "user2@test.com"
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password("password"),
                    role=UserRole.User,
                    status=UserStatus.active,
                )
            )
            db.commit()
    finally:
        db.close()
    return _login(client, email)


# ---------- experience journeys ----------


def test_experience_journey_requires_user_role(
    client, user_token, author_token, moderator_token
):
    exp_id = _create_published_experience_with_points("rolereq")
    for tok in (author_token, moderator_token):
        r = client.post(f"/journeys/experience/{exp_id}/start", headers=_h(tok))
        assert r.status_code == 403, r.text


def test_start_experience_journey_requires_purchase_access(client, user_token):
    exp_id = _create_published_experience_with_points("noacc")
    r = client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    assert r.status_code == 403


def test_start_experience_journey_after_paid_access(client, user_token):
    exp_id = _create_published_experience_with_points("paid")
    _buy_access(client, user_token, exp_id)
    r = client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "started"
    assert data["journey_type"] == "experience"
    assert data["target_id"] == exp_id
    assert data["completed_points"] == []


def test_start_experience_journey_idempotent_for_active_journey(client, user_token):
    exp_id = _create_published_experience_with_points("idem")
    _buy_access(client, user_token, exp_id)
    r1 = client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    r2 = client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_start_experience_journey_requires_points(client, user_token):
    exp_id = _create_published_experience_no_points()
    _buy_access(client, user_token, exp_id)
    r = client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    assert r.status_code == 400


def test_experience_journey_progress(client, user_token):
    exp_id = _create_published_experience_with_points("prog")
    _buy_access(client, user_token, exp_id)
    client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    pts = _get_experience_points(exp_id)
    r = client.post(
        f"/journeys/experience/{exp_id}/progress",
        json={"point_id": pts[0]},
        headers=_h(user_token),
    )
    assert r.status_code == 200
    cp = [c["point_id"] for c in r.json()["completed_points"]]
    assert pts[0] in cp


def test_experience_journey_progress_rejects_wrong_point(client, user_token):
    exp_id1 = _create_published_experience_with_points("p1")
    exp_id2 = _create_published_experience_with_points("p2")
    _buy_access(client, user_token, exp_id1)
    client.post(f"/journeys/experience/{exp_id1}/start", headers=_h(user_token))
    foreign_point = _get_experience_points(exp_id2)[0]
    r = client.post(
        f"/journeys/experience/{exp_id1}/progress",
        json={"point_id": foreign_point},
        headers=_h(user_token),
    )
    assert r.status_code in (400, 404)


def test_experience_journey_progress_idempotent_same_point(client, user_token):
    exp_id = _create_published_experience_with_points("idempt")
    _buy_access(client, user_token, exp_id)
    client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    pid = _get_experience_points(exp_id)[0]
    client.post(
        f"/journeys/experience/{exp_id}/progress",
        json={"point_id": pid},
        headers=_h(user_token),
    )
    r = client.post(
        f"/journeys/experience/{exp_id}/progress",
        json={"point_id": pid},
        headers=_h(user_token),
    )
    assert r.status_code == 200
    assert len(r.json()["completed_points"]) == 1


def test_complete_experience_journey(client, user_token):
    exp_id = _create_published_experience_with_points("comp")
    _buy_access(client, user_token, exp_id)
    client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    pid = _get_experience_points(exp_id)[0]
    client.post(
        f"/journeys/experience/{exp_id}/progress",
        json={"point_id": pid},
        headers=_h(user_token),
    )
    r = client.post(f"/journeys/experience/{exp_id}/complete", headers=_h(user_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "completed"
    assert data["finished_at"] is not None


def test_complete_experience_journey_without_started(client, user_token):
    exp_id = _create_published_experience_with_points("nostart")
    _buy_access(client, user_token, exp_id)
    r = client.post(f"/journeys/experience/{exp_id}/complete", headers=_h(user_token))
    assert r.status_code == 400


def test_experience_journey_unknown_experience(client, user_token):
    r = client.post("/journeys/experience/9999999/start", headers=_h(user_token))
    assert r.status_code == 404


# ---------- reviews ----------


def _complete_experience_flow(client, token, exp_id: int) -> int:
    """Returns journey id after start -> complete."""
    r = client.post(f"/journeys/experience/{exp_id}/start", headers=_h(token))
    assert r.status_code == 200, r.text
    journey_id = r.json()["id"]
    r = client.post(f"/journeys/experience/{exp_id}/complete", headers=_h(token))
    assert r.status_code == 200, r.text
    return journey_id


def _complete_route_flow(client, token) -> tuple[int, int]:
    """Create route + point, start, progress, complete. Returns (route_id, journey_id)."""
    r = client.post("/me/routes", json={"name": "r"}, headers=_h(token))
    assert r.status_code in (200, 201), r.text
    route_id = r.json()["id"]
    r = client.post(
        f"/me/routes/{route_id}/points", json={"title": "p"}, headers=_h(token)
    )
    assert r.status_code in (200, 201)
    pid = r.json()["id"]
    r = client.post(f"/journeys/route/{route_id}/start", headers=_h(token))
    assert r.status_code == 200, r.text
    journey_id = r.json()["id"]
    client.post(
        f"/journeys/route/{route_id}/progress",
        json={"point_id": pid},
        headers=_h(token),
    )
    r = client.post(f"/journeys/route/{route_id}/complete", headers=_h(token))
    assert r.status_code == 200, r.text
    return route_id, journey_id


def test_review_requires_user_role(client, author_token, moderator_token):
    body = {
        "target_type": "experience",
        "target_id": 1,
        "journey_id": 1,
        "rating": 5,
        "text": "x",
    }
    for tok in (author_token, moderator_token):
        r = client.post("/reviews", json=body, headers=_h(tok))
        assert r.status_code == 403


def test_review_requires_completed_journey(client, user_token):
    exp_id = _create_published_experience_with_points("revstart")
    _buy_access(client, user_token, exp_id)
    r = client.post(f"/journeys/experience/{exp_id}/start", headers=_h(user_token))
    journey_id = r.json()["id"]
    body = {
        "target_type": "experience",
        "target_id": exp_id,
        "journey_id": journey_id,
        "rating": 5,
        "text": "good",
    }
    r = client.post("/reviews", json=body, headers=_h(user_token))
    assert r.status_code == 400


def test_create_review_after_completed_experience_journey(client, user_token):
    exp_id = _create_published_experience_with_points("revexp")
    _buy_access(client, user_token, exp_id)
    journey_id = _complete_experience_flow(client, user_token, exp_id)
    body = {
        "target_type": "experience",
        "target_id": exp_id,
        "journey_id": journey_id,
        "rating": 5,
        "text": "Отличное впечатление",
    }
    r = client.post("/reviews", json=body, headers=_h(user_token))
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["rating"] == 5
    assert data["text"] == "Отличное впечатление"
    assert data["target_type"] == "experience"
    assert data["target_id"] == exp_id
    assert data["journey_id"] == journey_id


def test_create_review_after_completed_route_journey(client, user_token):
    route_id, journey_id = _complete_route_flow(client, user_token)
    body = {
        "target_type": "route",
        "target_id": route_id,
        "journey_id": journey_id,
        "rating": 4,
        "text": "nice",
    }
    r = client.post("/reviews", json=body, headers=_h(user_token))
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["target_type"] == "route"
    assert data["rating"] == 4


def test_review_duplicate_rejected(client, user_token):
    exp_id = _create_published_experience_with_points("revdup")
    _buy_access(client, user_token, exp_id)
    journey_id = _complete_experience_flow(client, user_token, exp_id)
    body = {
        "target_type": "experience",
        "target_id": exp_id,
        "journey_id": journey_id,
        "rating": 5,
        "text": "a",
    }
    r1 = client.post("/reviews", json=body, headers=_h(user_token))
    assert r1.status_code in (200, 201)
    r2 = client.post("/reviews", json=body, headers=_h(user_token))
    assert r2.status_code == 400


def test_review_rejects_target_mismatch(client, user_token):
    exp_id = _create_published_experience_with_points("revmm")
    _buy_access(client, user_token, exp_id)
    journey_id = _complete_experience_flow(client, user_token, exp_id)
    body = {
        "target_type": "experience",
        "target_id": exp_id + 99999,  # wrong target_id
        "journey_id": journey_id,
        "rating": 5,
        "text": "x",
    }
    r = client.post("/reviews", json=body, headers=_h(user_token))
    assert r.status_code == 400


def test_review_foreign_journey_hidden(client, user_token):
    exp_id = _create_published_experience_with_points("revforeign")
    _buy_access(client, user_token, exp_id)
    journey_id = _complete_experience_flow(client, user_token, exp_id)

    token2 = _create_second_user(client)
    body = {
        "target_type": "experience",
        "target_id": exp_id,
        "journey_id": journey_id,
        "rating": 5,
        "text": "x",
    }
    r = client.post("/reviews", json=body, headers=_h(token2))
    assert r.status_code == 404


def test_review_rating_validation(client, user_token):
    exp_id = _create_published_experience_with_points("revrate")
    _buy_access(client, user_token, exp_id)
    journey_id = _complete_experience_flow(client, user_token, exp_id)
    for bad in (0, 6):
        body = {
            "target_type": "experience",
            "target_id": exp_id,
            "journey_id": journey_id,
            "rating": bad,
            "text": "x",
        }
        r = client.post("/reviews", json=body, headers=_h(user_token))
        assert r.status_code in (400, 422), f"rating={bad}: {r.status_code}"


# ---------- analytics ----------


def test_analytics_events_requires_auth(client):
    r = client.post(
        "/analytics/events",
        json={
            "event_name": "x",
            "session_id": "s",
            "source_app": "mobile",
        },
    )
    assert r.status_code == 401


def test_analytics_events_accepts_user_author_moderator(
    client, user_token, author_token, moderator_token
):
    body = {
        "event_name": "catalog_opened",
        "session_id": f"sess-{uuid.uuid4().hex[:6]}",
        "source_app": "mobile",
        "entity_type": "catalog",
        "entity_id": None,
        "payload": {"page": 1},
    }
    for tok in (user_token, author_token, moderator_token):
        r = client.post("/analytics/events", json=body, headers=_h(tok))
        assert r.status_code == 200, r.text
        assert r.json()["accepted"] == 1


def test_analytics_events_validation(client, user_token):
    bad_payloads = [
        {"event_name": "", "session_id": "s", "source_app": "m"},
        {"event_name": "x", "session_id": "", "source_app": "m"},
        {"event_name": "x", "session_id": "s", "source_app": ""},
    ]
    for body in bad_payloads:
        r = client.post("/analytics/events", json=body, headers=_h(user_token))
        assert r.status_code in (400, 422), f"{body}: {r.status_code}"


def test_analytics_events_batch(client, user_token):
    body = {
        "events": [
            {
                "event_name": "catalog_opened",
                "session_id": "sess-batch",
                "source_app": "mobile",
            },
            {
                "event_name": "order_created",
                "session_id": "sess-batch",
                "source_app": "mobile",
            },
        ]
    }
    r = client.post("/analytics/events", json=body, headers=_h(user_token))
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 2


def test_analytics_report_requires_moderator(
    client, user_token, author_token, moderator_token
):
    for tok in (user_token, author_token):
        r = client.get("/analytics/reports/basic", headers=_h(tok))
        assert r.status_code == 403, r.text
    r = client.get("/analytics/reports/basic", headers=_h(moderator_token))
    assert r.status_code == 200


def test_analytics_report_counts_events(client, user_token, moderator_token):
    # baseline
    base = client.get("/analytics/reports/basic", headers=_h(moderator_token)).json()
    base_total = base["total_events"]
    base_by_name = base["events_by_name"]

    unique_event = f"ev_{uuid.uuid4().hex[:8]}"
    for _ in range(3):
        client.post(
            "/analytics/events",
            json={
                "event_name": unique_event,
                "session_id": "s",
                "source_app": "mobile",
            },
            headers=_h(user_token),
        )

    r = client.get("/analytics/reports/basic", headers=_h(moderator_token))
    assert r.status_code == 200
    data = r.json()
    assert data["total_events"] >= base_total + 3
    assert data["events_by_name"].get(unique_event) == 3 + base_by_name.get(
        unique_event, 0
    )
