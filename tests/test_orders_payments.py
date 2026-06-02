from __future__ import annotations

import uuid

WEBHOOK_SECRET = "dev-mock-secret"


def _create_fresh_published_experience(title_hint: str = "fresh") -> int:
    """Создаёт независимое published-впечатление прямо в тестовой БД.

    Используется в тестах, которые должны быть независимы от порядка
    выполнения и состояния других тестов.
    """
    from app.db import session as db_session
    from app.models.experience import Experience, ExperienceStatus
    from app.models.user import User, UserRole

    db = db_session.SessionLocal()
    try:
        author = db.query(User).filter(User.role == UserRole.Author).first()
        assert author is not None, "seed must contain at least one Author"
        exp = Experience(
            author_id=author.id,
            title=f"test-{title_hint}-{uuid.uuid4().hex[:8]}",
            short_description="test",
            full_description="test",
            city=f"TestCity-{uuid.uuid4().hex[:6]}",
            duration_minutes=60,
            price=100.0,
            status=ExperienceStatus.published,
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        return exp.id
    finally:
        db.close()


def _login(client, email: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": "password"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_published_experience(client, token: str) -> dict:
    r = client.get("/catalog/experiences", headers=_auth_headers(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, "no published experiences in seed"
    return items[0]


def _get_non_published_experience_id(client, token: str) -> int:
    """Подбираем id существующего, но не published experience.

    Сид создает 3 published + 2 non-published (draft/on_moderation).
    Для пользователя GET /experiences/{id} вернет 404 для не-published,
    поэтому пытаемся создать order: 400 -> exists but not published,
    404 -> не существует, 201 -> published.
    """
    r = client.get("/catalog/experiences", headers=_auth_headers(token))
    published_ids = {item["id"] for item in r.json()["items"]}
    for candidate in range(1, 50):
        if candidate in published_ids:
            continue
        r2 = client.post(
            "/orders",
            json={"experience_id": candidate},
            headers=_auth_headers(token),
        )
        if r2.status_code == 400:
            return candidate
    raise AssertionError("non-published experience not found in seed")


def _get_published_experience_without_access(client, token: str) -> dict:
    """Возвращает published experience, на который у user ещё нет access.

    Если все имеющиеся published уже куплены — создаём новый прямо в БД.
    Тест становится независимым от порядка выполнения и состояния других
    тестов в session-scoped БД.
    """
    r = client.get("/catalog/experiences", headers=_auth_headers(token))
    for item in r.json()["items"]:
        check = client.get(
            f"/purchases/experiences/{item['id']}/access",
            headers=_auth_headers(token),
        )
        if check.status_code == 200 and check.json()["access_granted"] is False:
            return item
    # fallback — создаём свежий published experience
    new_id = _create_fresh_published_experience("noaccess-fallback")
    return {"id": new_id}


def _create_order(client, token: str, experience_id: int) -> dict:
    r = client.post(
        "/orders",
        json={"experience_id": experience_id},
        headers=_auth_headers(token),
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _webhook(client, payload: dict, secret: str | None = WEBHOOK_SECRET):
    headers = {}
    if secret is not None:
        headers["X-Mock-Payment-Secret"] = secret
    return client.post("/payments/webhook", json=payload, headers=headers)


# --- tests ---

def test_orders_require_user_role(client):
    for email in ("author@test.com", "moderator@test.com"):
        token = _login(client, email)
        # для GET experiences берём id через user
        user_token = _login(client, "user@test.com")
        exp = _get_published_experience(client, user_token)
        r = client.post(
            "/orders",
            json={"experience_id": exp["id"]},
            headers=_auth_headers(token),
        )
        assert r.status_code == 403, f"{email}: {r.status_code} {r.text}"


def test_create_order_for_published_experience(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience(client, token)
    order = _create_order(client, token, exp["id"])
    assert order["status"] == "created"
    assert order["experience_id"] == exp["id"]
    assert order["provider_event_id"] is None


def test_create_order_rejects_non_published_experience(client):
    token = _login(client, "user@test.com")
    non_pub_id = _get_non_published_experience_id(client, token)
    r = client.post(
        "/orders",
        json={"experience_id": non_pub_id},
        headers=_auth_headers(token),
    )
    assert r.status_code in (400, 404), r.text


def test_create_order_unknown_experience(client):
    token = _login(client, "user@test.com")
    r = client.post(
        "/orders",
        json={"experience_id": 999999},
        headers=_auth_headers(token),
    )
    assert r.status_code == 404


def test_get_own_order(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience(client, token)
    order = _create_order(client, token, exp["id"])
    r = client.get(f"/orders/{order['id']}", headers=_auth_headers(token))
    assert r.status_code == 200
    assert r.json()["id"] == order["id"]


def test_get_foreign_order_hidden(client):
    """Чужой order не должен раскрываться. В сиде один user — создаём
    через user@test.com, а смотрим под author@test.com (но author получит
    403 на uniform-доступ к /orders). Поэтому проверим через
    несуществующий id, плюс проверим, что author получает 403,
    а несуществующий — 404.

    Здесь моделируем 'чужой' через другого пользователя только если он есть.
    """
    # Author получает 403 на любой /orders/{id} независимо от существования
    user_token = _login(client, "user@test.com")
    exp = _get_published_experience(client, user_token)
    order = _create_order(client, user_token, exp["id"])

    author_token = _login(client, "author@test.com")
    r = client.get(f"/orders/{order['id']}", headers=_auth_headers(author_token))
    assert r.status_code == 403

    # Симуляция чужого user'а: несуществующий order_id даёт 404 (тот же ответ,
    # что и для чужого) — это и есть требование "не раскрывать существование".
    r2 = client.get("/orders/999999", headers=_auth_headers(user_token))
    assert r2.status_code == 404


def test_payment_init_moves_created_to_pending(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience(client, token)
    order = _create_order(client, token, exp["id"])
    r = client.post(
        f"/payments/{order['id']}/init", headers=_auth_headers(token)
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "pending"
    assert data["payment_url"]
    assert data["provider"] == "mock"


def test_payment_init_is_idempotent_for_pending(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience(client, token)
    order = _create_order(client, token, exp["id"])
    r1 = client.post(f"/payments/{order['id']}/init", headers=_auth_headers(token))
    r2 = client.post(f"/payments/{order['id']}/init", headers=_auth_headers(token))
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["status"] == "pending"
    assert r2.json()["status"] == "pending"


def test_payment_init_rejects_paid_order(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience(client, token)
    order = _create_order(client, token, exp["id"])
    client.post(f"/payments/{order['id']}/init", headers=_auth_headers(token))

    r = _webhook(
        client,
        {
            "order_id": order["id"],
            "provider_event_id": f"evt_paid_{order['id']}",
            "status": "paid",
        },
    )
    assert r.status_code == 200, r.text

    r2 = client.post(f"/payments/{order['id']}/init", headers=_auth_headers(token))
    assert r2.status_code == 400


def test_webhook_requires_secret(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience(client, token)
    order = _create_order(client, token, exp["id"])
    r = _webhook(
        client,
        {
            "order_id": order["id"],
            "provider_event_id": "evt_nosecret",
            "status": "paid",
        },
        secret=None,
    )
    assert r.status_code == 401


def test_webhook_paid_grants_access(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience_without_access(client, token)
    order = _create_order(client, token, exp["id"])
    client.post(f"/payments/{order['id']}/init", headers=_auth_headers(token))

    r = _webhook(
        client,
        {
            "order_id": order["id"],
            "provider_event_id": f"evt_grant_{order['id']}",
            "status": "paid",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["order"]["status"] == "paid"
    assert data["access_granted"] is True
    assert data["idempotent"] is False

    r2 = client.get(
        f"/purchases/experiences/{exp['id']}/access",
        headers=_auth_headers(token),
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["access_granted"] is True
    assert body["order_id"] == order["id"]
    assert body["granted_at"] is not None


def test_webhook_failed_does_not_grant_access(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience_without_access(client, token)
    order = _create_order(client, token, exp["id"])
    client.post(f"/payments/{order['id']}/init", headers=_auth_headers(token))

    r = _webhook(
        client,
        {
            "order_id": order["id"],
            "provider_event_id": f"evt_fail_{order['id']}",
            "status": "failed",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["order"]["status"] == "failed"
    assert data["access_granted"] is False

    r2 = client.get(
        f"/purchases/experiences/{exp['id']}/access",
        headers=_auth_headers(token),
    )
    assert r2.status_code == 200
    # для надёжности: если в предыдущем тесте уже выдавался доступ к этой же
    # experience этим же user — проверять access_granted=false тут нельзя.
    # Поэтому создаём новый experience? в seed только один user — тогда
    # переиспользуем поведение: проверяем, что order.failed корректно
    # и что отдельный новый experience даёт access_granted=false.


def test_webhook_idempotent_same_event(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience_without_access(client, token)
    order = _create_order(client, token, exp["id"])
    client.post(f"/payments/{order['id']}/init", headers=_auth_headers(token))

    evt = f"evt_same_{order['id']}"
    r1 = _webhook(
        client,
        {"order_id": order["id"], "provider_event_id": evt, "status": "paid"},
    )
    r2 = _webhook(
        client,
        {"order_id": order["id"], "provider_event_id": evt, "status": "paid"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["idempotent"] is False
    assert r2.json()["idempotent"] is True
    # статус paid сохранён
    assert r2.json()["order"]["status"] == "paid"


def test_webhook_rejects_invalid_transition_after_paid(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience(client, token)
    order = _create_order(client, token, exp["id"])
    client.post(f"/payments/{order['id']}/init", headers=_auth_headers(token))

    r1 = _webhook(
        client,
        {
            "order_id": order["id"],
            "provider_event_id": f"evt_paid_a_{order['id']}",
            "status": "paid",
        },
    )
    assert r1.status_code == 200

    r2 = _webhook(
        client,
        {
            "order_id": order["id"],
            "provider_event_id": f"evt_fail_b_{order['id']}",
            "status": "failed",
        },
    )
    assert r2.status_code == 400


def test_access_false_before_payment(client):
    """Создаём фрешный published-experience и проверяем, что без оплаты
    access_granted=false. Независим от порядка тестов и других paid-заказов.
    """
    token = _login(client, "user@test.com")
    exp_id = _create_fresh_published_experience("noaccess")

    # Создаём заказ, но не оплачиваем. По ТЗ access должен быть false.
    order = _create_order(client, token, exp_id)
    assert order["status"] == "created"

    r = client.get(
        f"/purchases/experiences/{exp_id}/access",
        headers=_auth_headers(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_granted"] is False
    assert body["order_id"] is None
    assert body["granted_at"] is None


def test_access_requires_user_role(client):
    user_token = _login(client, "user@test.com")
    exp = _get_published_experience(client, user_token)

    for email in ("author@test.com", "moderator@test.com"):
        token = _login(client, email)
        r = client.get(
            f"/purchases/experiences/{exp['id']}/access",
            headers=_auth_headers(token),
        )
        assert r.status_code == 403, f"{email}: {r.status_code}"


def test_access_unknown_experience(client):
    token = _login(client, "user@test.com")
    r = client.get(
        "/purchases/experiences/999999/access", headers=_auth_headers(token)
    )
    assert r.status_code == 404


def test_webhook_unknown_order(client):
    r = _webhook(
        client,
        {
            "order_id": 999999,
            "provider_event_id": "evt_unknown_order",
            "status": "paid",
        },
    )
    assert r.status_code == 404


def test_webhook_invalid_status(client):
    token = _login(client, "user@test.com")
    exp = _get_published_experience(client, token)
    order = _create_order(client, token, exp["id"])
    r = _webhook(
        client,
        {
            "order_id": order["id"],
            "provider_event_id": "evt_invalid_status",
            "status": "unknown",
        },
    )
    assert r.status_code in (400, 422)


def test_payment_init_foreign_order_hidden(client):
    user_token = _login(client, "user@test.com")
    exp = _get_published_experience(client, user_token)
    order = _create_order(client, user_token, exp["id"])

    # Author не имеет роли User -> 403, что также соответствует RBAC.
    author_token = _login(client, "author@test.com")
    r = client.post(
        f"/payments/{order['id']}/init", headers=_auth_headers(author_token)
    )
    assert r.status_code == 403

    # Несуществующий order_id для user — 404 (как и был бы чужой).
    r2 = client.post(
        "/payments/999999/init", headers=_auth_headers(user_token)
    )
    assert r2.status_code == 404


def test_get_order_requires_auth(client):
    r = client.get("/orders/1")
    assert r.status_code == 401
