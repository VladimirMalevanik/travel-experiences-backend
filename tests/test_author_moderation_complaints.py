from __future__ import annotations

import uuid

import pytest


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


def _valid_create_payload(hint: str = "exp") -> dict:
    return {
        "title": f"Author exp {hint} {uuid.uuid4().hex[:6]}",
        "short_description": "short",
        "full_description": "full description text",
        "city": f"City-{uuid.uuid4().hex[:6]}",
        "duration_minutes": 180,
        "price": 1500.0,
        "restrictions": "none",
        "points": [
            {"title": "P1", "description": "d1", "lat": 55.7, "lon": 37.6},
            {"title": "P2", "description": "d2", "lat": 55.8, "lon": 37.5},
        ],
    }


def _create_draft(client, author_token: str, hint: str = "exp") -> int:
    r = client.post(
        "/author/experiences", json=_valid_create_payload(hint), headers=_h(author_token)
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _count_audit(action: str) -> int:
    from app.db import session as db_session
    from app.models.audit import AuditLog

    with db_session.SessionLocal() as db:
        return db.query(AuditLog).filter(AuditLog.action == action).count()


def _count_analytics(event_name: str) -> int:
    from app.db import session as db_session
    from app.models.analytics import AnalyticsEvent

    with db_session.SessionLocal() as db:
        return (
            db.query(AnalyticsEvent)
            .filter(AnalyticsEvent.event_name == event_name)
            .count()
        )


def _make_second_author(client) -> str:
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.user import User, UserRole, UserStatus

    email = "author_other@test.com"
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password("password"),
                    role=UserRole.Author,
                    status=UserStatus.active,
                )
            )
            db.commit()
    finally:
        db.close()
    return _login(client, email)


def _seed_on_moderation_id() -> int:
    from app.db import session as db_session
    from app.models.experience import Experience, ExperienceStatus

    with db_session.SessionLocal() as db:
        exp = (
            db.query(Experience)
            .filter(Experience.status == ExperienceStatus.on_moderation)
            .first()
        )
        assert exp is not None
        return exp.id


# ========== Author ==========


def test_1_user_cannot_open_author_experiences(client, user_token):
    r = client.get("/author/experiences", headers=_h(user_token))
    assert r.status_code == 403


def test_2_moderator_cannot_open_author_experiences(client, moderator_token):
    r = client.get("/author/experiences", headers=_h(moderator_token))
    assert r.status_code == 403


def test_3_author_creates_draft(client, author_token):
    r = client.post(
        "/author/experiences", json=_valid_create_payload("draft"), headers=_h(author_token)
    )
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["status"] == "draft"
    assert data["author_id"] is not None
    assert len(data["points"]) == 2


def test_4_author_sees_only_own_experiences(client, author_token):
    other_token = _make_second_author(client)
    other_exp = _create_draft(client, other_token, "otherown")

    r = client.get("/author/experiences", headers=_h(author_token))
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()]
    assert other_exp not in ids


def test_5_author_edits_own_draft(client, author_token):
    exp_id = _create_draft(client, author_token, "edit")
    r = client.patch(
        f"/author/experiences/{exp_id}",
        json={"title": "Updated title"},
        headers=_h(author_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Updated title"


def test_6_author_cannot_edit_foreign_experience_404(client, author_token):
    other_token = _make_second_author(client)
    other_exp = _create_draft(client, other_token, "foreign")
    r = client.patch(
        f"/author/experiences/{other_exp}",
        json={"title": "hack"},
        headers=_h(author_token),
    )
    assert r.status_code == 404


def test_7_author_submit_draft_moves_to_on_moderation(client, author_token):
    exp_id = _create_draft(client, author_token, "submit")
    r = client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "on_moderation"


def test_8_submit_without_required_fields_or_points_rejected(client, author_token):
    # Create experience without points and without full_description.
    payload = {"title": "No points exp", "price": 0.0, "points": []}
    r = client.post("/author/experiences", json=payload, headers=_h(author_token))
    assert r.status_code in (200, 201), r.text
    exp_id = r.json()["id"]
    r = client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    assert r.status_code in (400, 422)


def test_9_author_cannot_set_published_directly(client, author_token):
    exp_id = _create_draft(client, author_token, "nopub")
    # Author update schema does not accept status; even if passed, ignored.
    r = client.patch(
        f"/author/experiences/{exp_id}",
        json={"status": "published"},
        headers=_h(author_token),
    )
    assert r.status_code in (200, 422)
    got = client.get(f"/author/experiences/{exp_id}", headers=_h(author_token))
    assert got.json()["status"] != "published"


# ========== Moderation ==========


def test_10_user_author_cannot_open_queue(client, user_token, author_token):
    for tok in (user_token, author_token):
        r = client.get("/moderation/queue", headers=_h(tok))
        assert r.status_code == 403


def test_11_moderator_sees_on_moderation_in_queue(client, author_token, moderator_token):
    exp_id = _create_draft(client, author_token, "queue")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    r = client.get("/moderation/queue", headers=_h(moderator_token))
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()["items"]]
    assert exp_id in ids
    assert all(item["status"] == "on_moderation" for item in r.json()["items"])


def test_12_moderator_publish_moves_to_published(client, author_token, moderator_token):
    exp_id = _create_draft(client, author_token, "pub")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    r = client.post(
        f"/moderation/experiences/{exp_id}/publish", headers=_h(moderator_token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"


def test_13_reject_requires_reason(client, author_token, moderator_token):
    exp_id = _create_draft(client, author_token, "rejreq")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    r = client.post(
        f"/moderation/experiences/{exp_id}/reject", json={}, headers=_h(moderator_token)
    )
    assert r.status_code in (400, 422)


def test_14_reject_moves_to_rejected_and_saves_reason(
    client, author_token, moderator_token
):
    exp_id = _create_draft(client, author_token, "rej")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    r = client.post(
        f"/moderation/experiences/{exp_id}/reject",
        json={"reason_code": "bad_content", "reason_text": "Не соответствует правилам"},
        headers=_h(moderator_token),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "rejected"
    assert data["moderation_reason_code"] == "bad_content"
    assert data["moderation_reason_text"] == "Не соответствует правилам"


def test_15_repeat_publish_reject_on_final_status_400(
    client, author_token, moderator_token
):
    exp_id = _create_draft(client, author_token, "final")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    client.post(f"/moderation/experiences/{exp_id}/publish", headers=_h(moderator_token))
    # already published -> publish again 400
    r1 = client.post(
        f"/moderation/experiences/{exp_id}/publish", headers=_h(moderator_token)
    )
    assert r1.status_code == 400
    # reject already published -> 400
    r2 = client.post(
        f"/moderation/experiences/{exp_id}/reject",
        json={"reason_code": "x", "reason_text": "y"},
        headers=_h(moderator_token),
    )
    assert r2.status_code == 400


def test_16_moderation_decision_created_on_publish_reject(
    client, author_token, moderator_token
):
    from app.db import session as db_session
    from app.models.moderation import ModerationDecision

    exp_id = _create_draft(client, author_token, "decision")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    client.post(f"/moderation/experiences/{exp_id}/publish", headers=_h(moderator_token))
    with db_session.SessionLocal() as db:
        count = (
            db.query(ModerationDecision)
            .filter(ModerationDecision.experience_id == exp_id)
            .count()
        )
    assert count >= 1


def test_17_audit_log_created_on_publish(client, author_token, moderator_token):
    before = _count_audit("moderation_publish")
    exp_id = _create_draft(client, author_token, "audit")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    client.post(f"/moderation/experiences/{exp_id}/publish", headers=_h(moderator_token))
    assert _count_audit("moderation_publish") >= before + 1


# ========== Complaints ==========


def _published_experience_id(client, user_token) -> int:
    r = client.get("/catalog/experiences", headers=_h(user_token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    return items[0]["id"]


def test_18_user_creates_complaint_on_experience(client, user_token):
    exp_id = _published_experience_id(client, user_token)
    r = client.post(
        "/complaints",
        json={
            "target_type": "experience",
            "target_id": exp_id,
            "reason_code": "inappropriate",
            "reason_text": "bad",
        },
        headers=_h(user_token),
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["status"] == "open"


def test_19_author_moderator_cannot_create_complaint(
    client, author_token, moderator_token, user_token
):
    exp_id = _published_experience_id(client, user_token)
    body = {
        "target_type": "experience",
        "target_id": exp_id,
        "reason_code": "x",
        "reason_text": "y",
    }
    for tok in (author_token, moderator_token):
        r = client.post("/complaints", json=body, headers=_h(tok))
        assert r.status_code == 403


def test_20_moderator_sees_complaint_in_list(client, user_token, moderator_token):
    exp_id = _published_experience_id(client, user_token)
    cr = client.post(
        "/complaints",
        json={"target_type": "experience", "target_id": exp_id, "reason_code": "r"},
        headers=_h(user_token),
    )
    cid = cr.json()["id"]
    r = client.get("/moderation/complaints", headers=_h(moderator_token))
    assert r.status_code == 200, r.text
    ids = [c["id"] for c in r.json()["items"]]
    assert cid in ids


def test_21_moderator_resolve_closes_complaint(client, user_token, moderator_token):
    exp_id = _published_experience_id(client, user_token)
    cr = client.post(
        "/complaints",
        json={"target_type": "experience", "target_id": exp_id, "reason_code": "r"},
        headers=_h(user_token),
    )
    cid = cr.json()["id"]
    r = client.post(
        f"/moderation/complaints/{cid}/resolve",
        json={"status": "resolved", "resolution_text": "handled"},
        headers=_h(moderator_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved"
    assert r.json()["resolved_at"] is not None


def test_22_repeat_resolve_closed_complaint_400(client, user_token, moderator_token):
    exp_id = _published_experience_id(client, user_token)
    cr = client.post(
        "/complaints",
        json={"target_type": "experience", "target_id": exp_id, "reason_code": "r"},
        headers=_h(user_token),
    )
    cid = cr.json()["id"]
    client.post(
        f"/moderation/complaints/{cid}/resolve",
        json={"status": "resolved", "resolution_text": "ok"},
        headers=_h(moderator_token),
    )
    r = client.post(
        f"/moderation/complaints/{cid}/resolve",
        json={"status": "rejected", "resolution_text": "again"},
        headers=_h(moderator_token),
    )
    assert r.status_code == 400


def test_23_user_author_cannot_open_moderation_complaints(
    client, user_token, author_token
):
    for tok in (user_token, author_token):
        r = client.get("/moderation/complaints", headers=_h(tok))
        assert r.status_code == 403


def test_24_audit_log_created_on_complaint_created_and_resolved(
    client, user_token, moderator_token
):
    created_before = _count_audit("complaint_created")
    resolved_before = _count_audit("complaint_resolved")
    exp_id = _published_experience_id(client, user_token)
    cr = client.post(
        "/complaints",
        json={"target_type": "experience", "target_id": exp_id, "reason_code": "r"},
        headers=_h(user_token),
    )
    cid = cr.json()["id"]
    client.post(
        f"/moderation/complaints/{cid}/resolve",
        json={"status": "resolved", "resolution_text": "ok"},
        headers=_h(moderator_token),
    )
    assert _count_audit("complaint_created") >= created_before + 1
    assert _count_audit("complaint_resolved") >= resolved_before + 1


# ========== Security / RBAC ==========


def test_25_rbac_enforced_for_author_moderation_complaints(
    client, user_token, author_token, moderator_token
):
    # /author/* only Author
    assert client.get("/author/experiences", headers=_h(user_token)).status_code == 403
    assert (
        client.get("/author/experiences", headers=_h(moderator_token)).status_code == 403
    )
    # /moderation/* only Moderator
    assert client.get("/moderation/queue", headers=_h(user_token)).status_code == 403
    assert client.get("/moderation/queue", headers=_h(author_token)).status_code == 403
    # /complaints only User
    body = {"target_type": "experience", "target_id": 1, "reason_code": "r"}
    assert client.post("/complaints", json=body, headers=_h(author_token)).status_code == 403


def test_26_foreign_author_experience_hidden_404(client, author_token):
    other_token = _make_second_author(client)
    other_exp = _create_draft(client, other_token, "hidden")
    r = client.get(f"/author/experiences/{other_exp}", headers=_h(author_token))
    assert r.status_code == 404


# ========== Analytics ==========


def test_27_author_created_submitted_in_analytics(client, author_token):
    created_before = _count_analytics("author_experience_created")
    submitted_before = _count_analytics("author_experience_submitted")
    exp_id = _create_draft(client, author_token, "ana")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    assert _count_analytics("author_experience_created") >= created_before + 1
    assert _count_analytics("author_experience_submitted") >= submitted_before + 1


def test_28_moderation_publish_reject_in_analytics(
    client, author_token, moderator_token
):
    pub_before = _count_analytics("moderation_publish")
    rej_before = _count_analytics("moderation_reject")

    exp_pub = _create_draft(client, author_token, "anapub")
    client.post(f"/author/experiences/{exp_pub}/submit", headers=_h(author_token))
    client.post(f"/moderation/experiences/{exp_pub}/publish", headers=_h(moderator_token))

    exp_rej = _create_draft(client, author_token, "anarej")
    client.post(f"/author/experiences/{exp_rej}/submit", headers=_h(author_token))
    client.post(
        f"/moderation/experiences/{exp_rej}/reject",
        json={"reason_code": "x", "reason_text": "y"},
        headers=_h(moderator_token),
    )
    assert _count_analytics("moderation_publish") >= pub_before + 1
    assert _count_analytics("moderation_reject") >= rej_before + 1


def test_29_complaint_created_resolved_in_analytics(
    client, user_token, moderator_token
):
    created_before = _count_analytics("complaint_created")
    resolved_before = _count_analytics("complaint_resolved")
    exp_id = _published_experience_id(client, user_token)
    cr = client.post(
        "/complaints",
        json={"target_type": "experience", "target_id": exp_id, "reason_code": "r"},
        headers=_h(user_token),
    )
    cid = cr.json()["id"]
    client.post(
        f"/moderation/complaints/{cid}/resolve",
        json={"status": "resolved", "resolution_text": "ok"},
        headers=_h(moderator_token),
    )
    assert _count_analytics("complaint_created") >= created_before + 1
    assert _count_analytics("complaint_resolved") >= resolved_before + 1


# ========== NFR / checks ==========


def test_30_catalog_config_has_server_side_config_and_filters(client, user_token):
    r = client.get("/catalog/config", headers=_h(user_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source"] == "server_config"
    assert "default_sort" in data and data["default_sort"]
    assert "supported_filters" in data and "city" in data["supported_filters"]
    assert "version" in data
    assert "priority_rules" in data or "showcase_priorities" in data


def test_31_catalog_time_window_returns_only_matching_published(client, user_token):
    # time_window_hours=6 -> max 360 minutes; all results published and within window.
    r = client.get(
        "/catalog/experiences",
        headers=_h(user_token),
        params={"time_window_hours": 6},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    for item in items:
        assert item["status"] == "published"
        if item["duration_minutes"] is not None:
            assert item["duration_minutes"] <= 360

    # Stable / reproducible: same request twice -> same order of ids.
    r2 = client.get(
        "/catalog/experiences",
        headers=_h(user_token),
        params={"time_window_hours": 6},
    )
    assert [i["id"] for i in items] == [i["id"] for i in r2.json()["items"]]


def test_after_rejected_resubmit_requires_moderation_again(
    client, author_token, moderator_token
):
    exp_id = _create_draft(client, author_token, "resub")
    client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    client.post(
        f"/moderation/experiences/{exp_id}/reject",
        json={"reason_code": "c", "reason_text": "t"},
        headers=_h(moderator_token),
    )
    # edit rejected, then submit again -> on_moderation, reason cleared
    client.patch(
        f"/author/experiences/{exp_id}",
        json={"full_description": "improved description"},
        headers=_h(author_token),
    )
    r = client.post(f"/author/experiences/{exp_id}/submit", headers=_h(author_token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "on_moderation"
    assert data["moderation_reason_code"] is None
