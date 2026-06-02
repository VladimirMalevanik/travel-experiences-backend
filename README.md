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
  api/                   HTTP-роутеры (auth, me, catalog, experiences, routes, journeys)
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
- `routes` — `GET/POST /me/routes`, `GET/PATCH/DELETE /me/routes/{route_id}`,
  `POST /me/routes/{route_id}/points`,
  `PATCH/DELETE /me/routes/{route_id}/points/{point_id}`,
  `POST /me/routes/{route_id}/reorder`
- `journeys` — `POST /journeys/route/{route_id}/start`,
  `POST /journeys/route/{route_id}/progress`,
  `POST /journeys/route/{route_id}/complete`

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

## Этап 3: Личные маршруты и прохождение личного маршрута

Что добавлено:

- Личные маршруты пользователя (роль `User`):
  - `GET /me/routes` — список своих маршрутов (sort: `updated_at DESC, id DESC`), с `points_count`.
  - `POST /me/routes` — создать маршрут (`name`, статус по умолчанию `draft`).
  - `GET /me/routes/{route_id}` — детали своего маршрута с точками, отсортированными по `order ASC`.
  - `PATCH /me/routes/{route_id}` — редактировать `name` и/или `status`.
  - `DELETE /me/routes/{route_id}` — удалить маршрут вместе с точками (204).
  - `POST /me/routes/{route_id}/points` — добавить точку. Если `order` не передан — `max(order)+1`. Лимит MVP: 30 точек на маршрут (иначе 400).
  - `PATCH /me/routes/{route_id}/points/{point_id}` — редактировать точку (`title`, `note`, `lat`, `lon`, `order`).
  - `DELETE /me/routes/{route_id}/points/{point_id}` — удалить точку (204).
  - `POST /me/routes/{route_id}/reorder` — пересортировка по списку `point_ids`. Список должен содержать **ровно все** существующие `id` точек маршрута без дублей и чужих — иначе 400. После reorder `order` выставляется с 1.
- Прохождение личного маршрута (роль `User`):
  - `POST /journeys/route/{route_id}/start` — начать прохождение. Если маршрут без точек → 400. Если уже есть `started` journey по этому маршруту — возвращается он же, без дубля. Если есть `completed` journey, новый `started` создать можно.
  - `POST /journeys/route/{route_id}/progress` — отметить прохождение точки. `point_id` должен принадлежать маршруту. Должен существовать `started` journey, иначе 400. Повторный progress по той же точке идемпотентен — дубль не создаётся.
  - `POST /journeys/route/{route_id}/complete` — завершить прохождение. Требуется `started` journey, иначе 400. Повторный `complete` для уже завершённого journey возвращает **400** (выбран явный конфликт состояния).
- RBAC: все эндпоинты `/me/routes/*` и `/journeys/route/*` доступны только роли `User`. Author/Moderator получают `403`. Чужие маршруты для User скрываются как `404` (факт существования не раскрывается).
- Бизнес-логирование: `route_created`, `route_updated`, `route_deleted`, `route_point_added/updated/deleted`, `route_reordered`, `route_journey_started/progress/completed`. Без токенов, паролей и чувствительных заметок.
- БД: новые миграции не требуются — модели `PersonalRoute`, `RoutePoint`, `Journey`, `JourneyProgress` уже существуют с этапа 1.

### Demo flow

```bash
# 1. Логин
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@test.com","password":"password"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

# 2. Создать маршрут
RID=$(curl -s -X POST http://127.0.0.1:8000/me/routes \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Weekend"}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 3. Добавить точки
P1=$(curl -s -X POST http://127.0.0.1:8000/me/routes/$RID/points \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"title":"Старт","lat":55.75,"lon":37.62}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
P2=$(curl -s -X POST http://127.0.0.1:8000/me/routes/$RID/points \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"title":"Финиш","lat":55.76,"lon":37.60}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')

# 4. Reorder
curl -s -X POST http://127.0.0.1:8000/me/routes/$RID/reorder \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"point_ids\":[$P2,$P1]}"

# 5. Start journey
curl -s -X POST http://127.0.0.1:8000/journeys/route/$RID/start -H "$AUTH"

# 6. Progress
curl -s -X POST http://127.0.0.1:8000/journeys/route/$RID/progress \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"point_id\":$P1}"

# 7. Complete
curl -s -X POST http://127.0.0.1:8000/journeys/route/$RID/complete -H "$AUTH"
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
| FR-07 | Личные маршруты            | **Реализовано** (этап 3): CRUD маршрутов и точек, reorder, лимит 30 точек, изоляция по владельцу. |
| FR-08 | Прохождение (journey)      | **Реализовано для личных маршрутов** (этап 3): start/progress/complete, восстановление прогресса. Для purchased experience запланировано после mock-платежей. |
| FR-09 | Кабинет автора             | Вне P0 до 2 июня. |
| FR-10 | Модерация                  | Вне P0 до 2 июня. |
| FR-11 | Жалобы                     | Вне P0 до 2 июня. |
| FR-12 | Отзывы                     | Модель подготовлена, API запланирован. |
| FR-13 | Аналитика                  | Модель подготовлена, API запланирован. |
| FR-14 | Логирование / аудит        | **Расширено** (этап 3): request-логирование + бизнес-логи каталога, карточки, CRUD маршрутов и journey-событий. |
| FR-15 | Конфиг каталога            | **Частично реализовано**: серверная сортировка по умолчанию + `GET /catalog/config` отдаёт текущий конфиг. |
