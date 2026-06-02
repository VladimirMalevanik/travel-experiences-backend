# Travel Experiences Backend

Backend service for a travel "experiences" app (course project):
catalog of ready-made travel experiences, purchase, guided journey
progress, and personal routes.

This repository contains **Stage 1** of the backend: project skeleton,
database models, migrations, seed data, authentication/RBAC, Swagger
and basic tests. Business endpoints (catalog, orders, journeys, etc.)
will be added in subsequent stages.

## Tech stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic v2 / pydantic-settings
- SQLite (local) via `sqlite:///./app.db`
- JWT auth (`python-jose`), password hashing (`passlib[bcrypt]`)
- Pytest + httpx (FastAPI `TestClient`)

## Project structure

```
app/
  main.py                FastAPI app, /health, router wiring, request logging
  api/                   HTTP routers (auth, me)
  core/                  config, security (JWT, hashing), logging
  db/                    SQLAlchemy Base, session, seed
  models/                ORM models (User, Experience, Route, Journey, Order, Review, Analytics)
  schemas/               Pydantic schemas
  services/              auth service + RBAC dependencies
alembic/                 migration environment
tests/                   pytest tests
```

## Setup

### 1. Create a virtual environment and install dependencies

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Create `.env`

Copy the example file and edit if needed:

```bash
cp .env.example .env
```

Defaults are fine for local SQLite development.

### 3. Apply migrations

Create the initial migration (only the first time):

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

Re-apply later changes with:

```bash
alembic upgrade head
```

> Note: if you just want to start quickly without Alembic, the seed
> script will also call `Base.metadata.create_all()` to create tables.

### 4. Seed the database

Idempotent — safe to run multiple times.

```bash
python -m app.db.seed
```

### 5. Run the backend

```bash
uvicorn app.main:app --reload
```

### 6. Open Swagger

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

Visible endpoint groups at Stage 1:

- `health` — `GET /health`
- `auth` — `POST /auth/login`, `POST /auth/refresh`
- `me` — `GET /me`

## Test users (seeded)

| Email                 | Password   | Role       |
|-----------------------|------------|------------|
| user@test.com         | password   | User       |
| author@test.com       | password   | Author     |
| moderator@test.com    | password   | Moderator  |

Login flow (for Swagger):
1. `POST /auth/login` with email/password → copy `access_token`.
2. Click "Authorize" in Swagger and paste the token.
3. Now `GET /me` and any future protected endpoints will work.

## Running tests

```bash
pytest
```

Tests use an isolated `test_app.db` SQLite file that is wiped between
sessions, seeded with the three test users and three Experiences.

## Current implementation status

Stage 1 (this commit) delivers:

- FastAPI app with `/health`, `/docs`, `/openapi.json`.
- DB models for all entities required by the spec: `User`, `Experience`,
  `ExperiencePoint`, `PersonalRoute`, `RoutePoint`, `Journey`,
  `JourneyProgress`, `Order`, `PurchaseAccess`, `Review`,
  `AnalyticsEvent`.
- Alembic environment configured against the same metadata.
- Idempotent seed script with 3 users + 3 published experiences (each
  with ≥ 2 `ExperiencePoint`).
- Auth/RBAC: password hashing (bcrypt), JWT access token, `POST
  /auth/login`, `POST /auth/refresh`, `GET /me`. Roles
  `User / Author / Moderator` are stored on the backend and cannot be
  set by the client. A `require_roles(...)` dependency is ready for
  future protected endpoints.
- Request logging middleware (method, path, status_code, latency_ms).
- Pytest suite covering health, login, /me, wrong password, missing token.

## MVP simplifications (Stage 1)

These shortcuts are intentional and will be revisited in later stages:

- `POST /auth/refresh` accepts a currently valid **access** token and
  issues a new access token (no separate refresh-token store yet).
- Single access-token type, no token revocation list.
- `AnalyticsEvent.payload` is stored as text (JSON-encoded in app code)
  rather than a native JSON column, for portability on SQLite.
- `JourneyProgress.point_id` is a plain integer (no FK) because
  journeys can point at either `ExperiencePoint` or `RoutePoint`
  depending on `journey_type`.
- `Journey.target_id` is a plain integer for the same polymorphic
  reason (kept simple at this stage).

## FR → implementation status

| FR    | Area                       | Stage 1 status |
|-------|----------------------------|----------------|
| FR-01 | Auth / RBAC                | **Partially implemented**: login, JWT auth, roles User/Author/Moderator, `GET /me`. |
| FR-02 | Catalog                    | Not implemented at Stage 1, planned for Stage 2. |
| FR-03 | Experience card            | Not implemented at Stage 1, planned for Stage 2. |
| FR-04 | Purchase published only    | Not implemented at Stage 1, planned for the mock-payment stage. |
| FR-05 | Orders / access            | Not implemented at Stage 1, planned for the mock-payment stage. |
| FR-06 | Webhook idempotency        | Not implemented at Stage 1, planned for the mock-payment stage. |
| FR-07 | Personal routes            | Models prepared; API planned for Stage 3. |
| FR-08 | Journey progress           | Models prepared; API planned for Stage 3. |
| FR-09 | Author cabinet             | Out of P0 scope until 2 June. |
| FR-10 | Moderation                 | Out of P0 scope until 2 June. |
| FR-11 | Complaints                 | Out of P0 scope until 2 June. |
| FR-12 | Reviews                    | Model prepared; API planned for the next stage. |
| FR-13 | Analytics                  | Model prepared; API planned for the next stage. |
| FR-14 | Logging / audit            | Basic request logging implemented. |
| FR-15 | Catalog config             | Not implemented at Stage 1, planned as backend default sorting. |
