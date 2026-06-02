from __future__ import annotations

from app.core.security import hash_password
from app.db import session as db_session
from app.models.experience import Experience, ExperienceStatus
from app.models.user import User, UserRole, UserStatus


def _login(client, email: str, password: str = "password") -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _draft_id(*, author_email: str = "author@test.com") -> int:
    with db_session.SessionLocal() as db:
        author = db.query(User).filter(User.email == author_email).first()
        exp = (
            db.query(Experience)
            .filter(
                Experience.status == ExperienceStatus.draft,
                Experience.author_id == author.id,
            )
            .first()
        )
        assert exp is not None, "В seed должен быть draft Experience для author@test.com"
        return exp.id


def test_catalog_requires_auth(client):
    r = client.get("/catalog/experiences")
    assert r.status_code == 401


def test_catalog_returns_only_published(client):
    token = _login(client, "user@test.com")
    r = client.get("/catalog/experiences", headers=_auth(token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data and "total" in data
    assert all(item["status"] == "published" for item in data["items"])
    assert data["total"] >= 3


def test_catalog_filter_city(client):
    token = _login(client, "user@test.com")
    r = client.get("/catalog/experiences", headers=_auth(token), params={"city": "Москва"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) > 0
    assert all(item["city"] == "Москва" for item in items)


def test_catalog_filter_duration_window(client):
    token = _login(client, "user@test.com")
    r = client.get(
        "/catalog/experiences",
        headers=_auth(token),
        params={"min_duration_minutes": 120, "max_duration_minutes": 360},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    for item in items:
        assert 120 <= item["duration_minutes"] <= 360


def test_catalog_filter_price_range(client):
    token = _login(client, "user@test.com")
    r = client.get(
        "/catalog/experiences",
        headers=_auth(token),
        params={"min_price": 0, "max_price": 5000},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    for item in items:
        assert 0 <= item["price"] <= 5000


def test_catalog_pagination(client):
    token = _login(client, "user@test.com")
    r = client.get(
        "/catalog/experiences",
        headers=_auth(token),
        params={"page": 1, "size": 2},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["page"] == 1
    assert data["size"] == 2
    assert len(data["items"]) <= 2
    assert data["total"] >= len(data["items"])


def test_catalog_rejects_too_large_size(client):
    token = _login(client, "user@test.com")
    r = client.get("/catalog/experiences", headers=_auth(token), params={"size": 1000})
    assert r.status_code in (400, 422)


def test_experience_card_published_visible_to_user(client):
    token = _login(client, "user@test.com")
    r = client.get("/catalog/experiences", headers=_auth(token))
    items = r.json()["items"]
    assert items, "В каталоге должны быть опубликованные впечатления"
    exp_id = items[0]["id"]

    r2 = client.get(f"/experiences/{exp_id}", headers=_auth(token))
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["id"] == exp_id
    assert data["purchase_available"] is True
    assert data["status"] == "published"
    assert "points" in data and len(data["points"]) >= 2
    orders = [p["order"] for p in data["points"]]
    assert orders == sorted(orders)


def test_experience_card_draft_hidden_from_user(client):
    token = _login(client, "user@test.com")
    draft_id = _draft_id()
    r = client.get(f"/experiences/{draft_id}", headers=_auth(token))
    assert r.status_code == 404


def test_experience_card_draft_visible_to_author_owner(client):
    token = _login(client, "author@test.com")
    draft_id = _draft_id()
    r = client.get(f"/experiences/{draft_id}", headers=_auth(token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "draft"
    assert data["purchase_available"] is False


def test_experience_card_draft_hidden_from_other_author(client):
    # Второй автор создаётся только для этого теста и в seed не попадает.
    other_email = "author2@test.com"
    with db_session.SessionLocal() as db:
        existing = db.query(User).filter(User.email == other_email).first()
        if existing is None:
            other = User(
                email=other_email,
                password_hash=hash_password("password"),
                role=UserRole.Author,
                status=UserStatus.active,
            )
            db.add(other)
            db.commit()

    token = _login(client, other_email)
    draft_id = _draft_id()
    r = client.get(f"/experiences/{draft_id}", headers=_auth(token))
    assert r.status_code == 404


def test_experience_card_non_published_visible_to_moderator(client):
    token = _login(client, "moderator@test.com")
    draft_id = _draft_id()
    r = client.get(f"/experiences/{draft_id}", headers=_auth(token))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["purchase_available"] is False
    assert data["status"] in ("draft", "on_moderation", "rejected")


def test_experience_not_found(client):
    token = _login(client, "user@test.com")
    r = client.get("/experiences/999999", headers=_auth(token))
    assert r.status_code == 404
