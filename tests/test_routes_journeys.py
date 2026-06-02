from __future__ import annotations

import pytest


def _login(client, email: str, password: str = "password") -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(token: str) -> dict:
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


def _create_second_user(client):
    """Create extra User via DB and return login token."""
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.user import User, UserRole, UserStatus

    email = "user2@test.com"
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u is None:
            u = User(
                email=email,
                password_hash=hash_password("password"),
                role=UserRole.User,
                status=UserStatus.active,
            )
            db.add(u)
            db.commit()
    finally:
        db.close()
    return _login(client, email)


def _create_route(client, token, name="My route") -> dict:
    r = client.post("/me/routes", json={"name": name}, headers=_headers(token))
    assert r.status_code in (200, 201), r.text
    return r.json()


def _add_point(client, token, route_id, title="P", **kwargs) -> dict:
    body = {"title": title, **kwargs}
    r = client.post(
        f"/me/routes/{route_id}/points", json=body, headers=_headers(token)
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


# 1
def test_routes_require_user_role(client, author_token, moderator_token):
    r = client.get("/me/routes", headers=_headers(author_token))
    assert r.status_code == 403
    r = client.get("/me/routes", headers=_headers(moderator_token))
    assert r.status_code == 403


# 2
def test_create_route(client, user_token):
    r = client.post("/me/routes", json={"name": "Trip"}, headers=_headers(user_token))
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["name"] == "Trip"
    assert data["points"] == []
    assert data["status"] == "draft"


# 3
def test_list_routes_only_own(client, user_token):
    own = _create_route(client, user_token, "MineOnly")
    token2 = _create_second_user(client)
    r = client.get("/me/routes", headers=_headers(token2))
    assert r.status_code == 200
    assert all(item["id"] != own["id"] for item in r.json())


# 4
def test_get_route_detail(client, user_token):
    route = _create_route(client, user_token, "Detail")
    _add_point(client, user_token, route["id"], title="A")
    _add_point(client, user_token, route["id"], title="B")
    r = client.get(f"/me/routes/{route['id']}", headers=_headers(user_token))
    assert r.status_code == 200
    pts = r.json()["points"]
    assert [p["order"] for p in pts] == sorted([p["order"] for p in pts])
    assert len(pts) == 2


# 5
def test_update_route(client, user_token):
    route = _create_route(client, user_token, "Old")
    r = client.patch(
        f"/me/routes/{route['id']}", json={"name": "New"}, headers=_headers(user_token)
    )
    assert r.status_code == 200
    assert r.json()["name"] == "New"


# 6
def test_delete_route(client, user_token):
    route = _create_route(client, user_token, "Doomed")
    r = client.delete(f"/me/routes/{route['id']}", headers=_headers(user_token))
    assert r.status_code == 204
    r = client.get(f"/me/routes/{route['id']}", headers=_headers(user_token))
    assert r.status_code == 404


# 7
def test_add_route_point(client, user_token):
    route = _create_route(client, user_token, "WithPt")
    p = _add_point(client, user_token, route["id"], title="Hello", note="n", lat=1.0, lon=2.0)
    assert p["title"] == "Hello"
    assert p["order"] == 1


# 8
def test_max_30_points(client, user_token):
    route = _create_route(client, user_token, "Many")
    for i in range(30):
        _add_point(client, user_token, route["id"], title=f"P{i}")
    r = client.post(
        f"/me/routes/{route['id']}/points",
        json={"title": "overflow"},
        headers=_headers(user_token),
    )
    assert r.status_code == 400


# 9
def test_update_route_point(client, user_token):
    route = _create_route(client, user_token, "UpdPt")
    p = _add_point(client, user_token, route["id"], title="Old")
    r = client.patch(
        f"/me/routes/{route['id']}/points/{p['id']}",
        json={"title": "NewTitle", "note": "nn"},
        headers=_headers(user_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "NewTitle"
    assert body["note"] == "nn"


# 10
def test_delete_route_point(client, user_token):
    route = _create_route(client, user_token, "DelPt")
    p = _add_point(client, user_token, route["id"], title="X")
    r = client.delete(
        f"/me/routes/{route['id']}/points/{p['id']}", headers=_headers(user_token)
    )
    assert r.status_code == 204
    r = client.get(f"/me/routes/{route['id']}", headers=_headers(user_token))
    assert all(pt["id"] != p["id"] for pt in r.json()["points"])


# 11
def test_reorder_points(client, user_token):
    route = _create_route(client, user_token, "Reorder")
    a = _add_point(client, user_token, route["id"], title="A")
    b = _add_point(client, user_token, route["id"], title="B")
    c = _add_point(client, user_token, route["id"], title="C")
    r = client.post(
        f"/me/routes/{route['id']}/reorder",
        json={"point_ids": [c["id"], b["id"], a["id"]]},
        headers=_headers(user_token),
    )
    assert r.status_code == 200
    pts = r.json()["points"]
    assert [p["id"] for p in pts] == [c["id"], b["id"], a["id"]]
    assert [p["order"] for p in pts] == [1, 2, 3]


# 12
def test_reorder_rejects_missing_or_duplicate_points(client, user_token):
    route = _create_route(client, user_token, "ReorderBad")
    a = _add_point(client, user_token, route["id"], title="A")
    b = _add_point(client, user_token, route["id"], title="B")
    # duplicate
    r = client.post(
        f"/me/routes/{route['id']}/reorder",
        json={"point_ids": [a["id"], a["id"]]},
        headers=_headers(user_token),
    )
    assert r.status_code == 400
    # missing
    r = client.post(
        f"/me/routes/{route['id']}/reorder",
        json={"point_ids": [a["id"]]},
        headers=_headers(user_token),
    )
    assert r.status_code == 400
    # alien id
    r = client.post(
        f"/me/routes/{route['id']}/reorder",
        json={"point_ids": [a["id"], b["id"], 9999999]},
        headers=_headers(user_token),
    )
    assert r.status_code == 400


# 13
def test_other_user_cannot_access_route(client, user_token):
    route = _create_route(client, user_token, "Private")
    token2 = _create_second_user(client)
    rid = route["id"]
    assert client.get(f"/me/routes/{rid}", headers=_headers(token2)).status_code == 404
    assert (
        client.patch(
            f"/me/routes/{rid}", json={"name": "x"}, headers=_headers(token2)
        ).status_code
        == 404
    )
    assert client.delete(f"/me/routes/{rid}", headers=_headers(token2)).status_code == 404


# 14
def test_start_route_journey(client, user_token):
    route = _create_route(client, user_token, "JStart")
    _add_point(client, user_token, route["id"], title="A")
    r = client.post(
        f"/journeys/route/{route['id']}/start", headers=_headers(user_token)
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "started"
    assert data["completed_points"] == []
    assert data["journey_type"] == "route"
    assert data["target_id"] == route["id"]


# 15
def test_start_route_journey_requires_points(client, user_token):
    route = _create_route(client, user_token, "Empty")
    r = client.post(
        f"/journeys/route/{route['id']}/start", headers=_headers(user_token)
    )
    assert r.status_code == 400


# 16
def test_route_journey_progress(client, user_token):
    route = _create_route(client, user_token, "Prog")
    p = _add_point(client, user_token, route["id"], title="A")
    client.post(f"/journeys/route/{route['id']}/start", headers=_headers(user_token))
    r = client.post(
        f"/journeys/route/{route['id']}/progress",
        json={"point_id": p["id"]},
        headers=_headers(user_token),
    )
    assert r.status_code == 200
    cp = [c["point_id"] for c in r.json()["completed_points"]]
    assert p["id"] in cp


# 17
def test_route_journey_progress_idempotent_for_same_point(client, user_token):
    route = _create_route(client, user_token, "Idem")
    p = _add_point(client, user_token, route["id"], title="A")
    client.post(f"/journeys/route/{route['id']}/start", headers=_headers(user_token))
    client.post(
        f"/journeys/route/{route['id']}/progress",
        json={"point_id": p["id"]},
        headers=_headers(user_token),
    )
    r = client.post(
        f"/journeys/route/{route['id']}/progress",
        json={"point_id": p["id"]},
        headers=_headers(user_token),
    )
    assert r.status_code == 200
    assert len(r.json()["completed_points"]) == 1


# 18
def test_route_journey_complete(client, user_token):
    route = _create_route(client, user_token, "Comp")
    p = _add_point(client, user_token, route["id"], title="A")
    client.post(f"/journeys/route/{route['id']}/start", headers=_headers(user_token))
    client.post(
        f"/journeys/route/{route['id']}/progress",
        json={"point_id": p["id"]},
        headers=_headers(user_token),
    )
    r = client.post(
        f"/journeys/route/{route['id']}/complete", headers=_headers(user_token)
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert data["finished_at"] is not None


# 19
def test_route_journey_complete_without_started(client, user_token):
    route = _create_route(client, user_token, "NoStart")
    _add_point(client, user_token, route["id"], title="A")
    r = client.post(
        f"/journeys/route/{route['id']}/complete", headers=_headers(user_token)
    )
    assert r.status_code == 400


# 20
def test_author_moderator_cannot_start_route_journey(
    client, user_token, author_token, moderator_token
):
    route = _create_route(client, user_token, "RoleGuard")
    _add_point(client, user_token, route["id"], title="A")
    assert (
        client.post(
            f"/journeys/route/{route['id']}/start", headers=_headers(author_token)
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/journeys/route/{route['id']}/start",
            headers=_headers(moderator_token),
        ).status_code
        == 403
    )


# 21
def test_other_user_cannot_start_or_progress_foreign_route(client, user_token):
    route = _create_route(client, user_token, "Foreign")
    p = _add_point(client, user_token, route["id"], title="A")
    token2 = _create_second_user(client)
    assert (
        client.post(
            f"/journeys/route/{route['id']}/start", headers=_headers(token2)
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/journeys/route/{route['id']}/progress",
            json={"point_id": p["id"]},
            headers=_headers(token2),
        ).status_code
        == 404
    )
