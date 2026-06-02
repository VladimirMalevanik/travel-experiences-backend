# Travel Experiences Backend

Бэкенд трэвел-приложения «впечатлений» (курсовой проект):
каталог готовых впечатлений, покупка, сопровождение прохождения и
личные маршруты.

## Стек

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic v2 / pydantic-settings
- SQLite (локально) через `sqlite:///./app.db`
- JWT-аутентификация (`python-jose`), хеширование паролей (`bcrypt`)
- Pytest + httpx (FastAPI `TestClient`)

## Структура проекта

```
app/
  main.py                FastAPI-приложение, /health, подключение роутеров, request-логирование
  api/                   HTTP-роутеры (auth, me, catalog, experiences)
  core/                  конфиг, security (JWT, хеширование), логирование
  db/                    SQLAlchemy Base, сессия, seed
  models/                ORM-модели (User, Experience, Route, Journey, Order, Review, Analytics)
  schemas/               Pydantic-схемы
  services/              auth-сервис и RBAC-зависимости
alembic/                 миграции
tests/                   тесты pytest
```

## Установка

### 1. Виртуальное окружение и зависимости

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Конфиг `.env`

```bash
cp .env.example .env
```

Для локальной SQLite дефолтов достаточно.

### 3. Миграции

```bash
alembic upgrade head
```

Если миграция ещё не создана:

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

> Можно стартовать и без Alembic — seed-скрипт сам вызовет
> `Base.metadata.create_all()`.

### 4. Seed

Идемпотентный, безопасно запускать повторно.

```bash
python -m app.db.seed
```

### 5. Запуск

```bash
uvicorn app.main:app --reload
```

### 6. Swagger

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

Группы endpoints:

- `health` — `GET /health`
- `auth` — `POST /auth/login`, `POST /auth/refresh`
- `me` — `GET /me`
- `catalog` — `GET /catalog/experiences`, `GET /catalog/config`
- `experiences` — `GET /experiences/{id}`

## Тестовые пользователи (seed)

| Email              | Пароль   | Роль       |
|--------------------|----------|------------|
| user@test.com      | password | User       |
| author@test.com    | password | Author     |
| moderator@test.com | password | Moderator  |

Логин через Swagger:
1. `POST /auth/login` с email/паролем → скопировать `access_token`.
2. Нажать «Authorize» в Swagger и вставить токен.
3. После этого работают `GET /me` и остальные защищённые endpoints.

## Запуск тестов

```bash
pytest
```

Тесты используют изолированный `test_app.db`, который пересоздаётся
между сессиями и сидится тремя тестовыми пользователями плюс набором
впечатлений (published / draft / on_moderation).

## Этап 1: каркас и аутентификация

- FastAPI-приложение с `/health`, `/docs`, `/openapi.json`.
- ORM-модели всех сущностей из ТЗ: `User`, `Experience`,
  `ExperiencePoint`, `PersonalRoute`, `RoutePoint`, `Journey`,
  `JourneyProgress`, `Order`, `PurchaseAccess`, `Review`,
  `AnalyticsEvent`.
- Alembic-окружение, подключённое к той же метадате.
- Идемпотентный seed-скрипт.
- Auth/RBAC: хеширование паролей через `bcrypt`, JWT access-token,
  `POST /auth/login`, `POST /auth/refresh`, `GET /me`. Роли
  `User / Author / Moderator` хранятся на бэкенде и не задаются
  клиентом. Готова зависимость `require_roles(...)` для будущих
  защищённых endpoints.
- Middleware request-логирования (method, path, status_code, latency_ms).

### Упрощения этапа 1 (MVP)

- `POST /auth/refresh` принимает действующий **access**-токен и
  выдаёт новый access (без отдельного refresh-хранилища).
- Один тип access-токена, без revocation-list.
- `AnalyticsEvent.payload` хранится как текст (JSON-строка), без
  нативного JSON-типа — для портативности SQLite.
- `JourneyProgress.point_id` и `Journey.target_id` — обычные
  integer-поля без FK, потому что `journey_type` полиморфно ссылается
  на `ExperiencePoint` либо `RoutePoint`.

## Этап 2: каталог и карточка впечатления

Что добавлено:

- `GET /catalog/experiences` — пагинированный каталог только
  **published**-впечатлений с фильтрами `city`,
  `min_duration_minutes`, `max_duration_minutes`, `min_price`,
  `max_price`, `page` (≥ 1), `size` (1–50). Серверная сортировка:
  `city ASC, duration_minutes ASC, id ASC`. Клиентский `sort` не
  принимается.
- `GET /experiences/{id}` — карточка впечатления с заголовком,
  описаниями, городом, длительностью, ценой, ограничениями,
  статусом, точками в порядке `order ASC` и вычисляемым флагом
  `purchase_available: bool` (true только если
  `status == "published"`).
- `GET /catalog/config` — диагностический endpoint, отдающий
  текущий backend-конфиг каталога: `default_sort`, `max_page_size`,
  `source`.
- Правила видимости non-published впечатлений (draft /
  on_moderation / rejected):
  - User → 404 (факт существования не раскрывается).
  - Author → 200 только для своих
    (`experience.author_id == current_user.id`), иначе 404.
  - Moderator → 200 для любого non-published.
- Бизнес-логирование запросов каталога (фильтры, page, size, total,
  returned) и карточки (`experience_id`, `experience_status`,
  `purchase_available`).
- Seed расширен: добавлены draft и on_moderation впечатления,
  принадлежащие `author@test.com`, для проверки видимости.

### Примеры curl

Логин и сохранение токена:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@test.com","password":"password"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

Каталог (только published):

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/catalog/experiences
```

Каталог с фильтром по городу:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/catalog/experiences?city=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0&page=1&size=10"
```

Карточка впечатления:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/experiences/1
```

Конфиг каталога:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/catalog/config
```

## FR → статус реализации

| FR    | Область                    | Статус |
|-------|----------------------------|--------|
| FR-01 | Auth / RBAC                | **Частично реализовано**: login, JWT, роли User/Author/Moderator, `GET /me`. |
| FR-02 | Каталог                    | **Реализовано** (этап 2): `GET /catalog/experiences` с фильтрами и пагинацией. |
| FR-03 | Карточка впечатления       | **Реализовано** (этап 2): `GET /experiences/{id}` с `purchase_available` и точками. |
| FR-04 | Покупка только published   | Не реализовано, запланировано на этап mock-платежей. |
| FR-05 | Заказы / доступ            | Не реализовано, запланировано на этап mock-платежей. |
| FR-06 | Идемпотентность webhook    | Не реализовано, запланировано на этап mock-платежей. |
| FR-07 | Личные маршруты            | Модели подготовлены, API запланирован. |
| FR-08 | Прохождение (journey)      | Модели подготовлены, API запланирован. |
| FR-09 | Кабинет автора             | Вне P0 до 2 июня. |
| FR-10 | Модерация                  | Вне P0 до 2 июня. |
| FR-11 | Жалобы                     | Вне P0 до 2 июня. |
| FR-12 | Отзывы                     | Модель подготовлена, API запланирован. |
| FR-13 | Аналитика                  | Модель подготовлена, API запланирован. |
| FR-14 | Логирование / аудит        | Базовое request-логирование + бизнес-логи каталога и карточки. |
| FR-15 | Конфиг каталога            | **Частично реализовано**: серверная сортировка по умолчанию + `GET /catalog/config` отдаёт текущий конфиг. |
