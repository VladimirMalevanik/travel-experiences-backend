import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base  # noqa: F401


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    from app.db import session as db_session

    test_engine = create_engine(
        "sqlite:///./test_app.db", connect_args={"check_same_thread": False}, future=True
    )
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

    # Подменяем глобальный engine и SessionLocal на тестовые
    db_session.engine = test_engine
    db_session.SessionLocal = TestSession

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    from app.db.seed import seed_experiences, seed_users

    db = TestSession()
    try:
        users = seed_users(db)
        seed_experiences(db, users["author@test.com"])
        db.commit()
    finally:
        db.close()

    yield

    Base.metadata.drop_all(bind=test_engine)
    try:
        Path("./test_app.db").unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    return TestClient(app)
