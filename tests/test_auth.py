def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_login_user(client):
    r = client.post("/auth/login", json={"email": "user@test.com", "password": "password"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str) and data["access_token"]


def test_me_user(client):
    r = client.post("/auth/login", json={"email": "user@test.com", "password": "password"})
    token = r.json()["access_token"]
    r2 = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["email"] == "user@test.com"
    assert data["role"] == "User"


def test_login_wrong_password(client):
    r = client.post("/auth/login", json={"email": "user@test.com", "password": "wrong"})
    assert r.status_code == 401


def test_me_without_token(client):
    r = client.get("/me")
    assert r.status_code == 401
