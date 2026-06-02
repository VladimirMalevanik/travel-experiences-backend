"""Идемпотентный seed-скрипт. Запуск: python -m app.db.seed"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.base import Base  # noqa: F401
from app.db.session import SessionLocal, engine
from app.models.experience import Experience, ExperiencePoint, ExperienceStatus
from app.models.user import User, UserRole, UserStatus


SEED_USERS = [
    {"email": "user@test.com", "password": "password", "role": UserRole.User},
    {"email": "author@test.com", "password": "password", "role": UserRole.Author},
    {"email": "moderator@test.com", "password": "password", "role": UserRole.Moderator},
]


SEED_EXPERIENCES: list[dict] = [
    {
        "title": "Прогулка по историческому центру Москвы",
        "short_description": "Пешеходный маршрут по историческим улицам центра Москвы.",
        "full_description": "Знакомство с ключевыми улицами и площадями исторического центра Москвы.",
        "city": "Москва",
        "duration_minutes": 150,
        "price": 1500.0,
        "restrictions": "Рекомендуется удобная обувь для долгой ходьбы.",
        "points": [
            {"order": 1, "title": "Красная площадь",
             "description": "Стартовая точка на Красной площади.",
             "lat": 55.7539, "lon": 37.6208},
            {"order": 2, "title": "Тверская улица",
             "description": "Прогулка по главной улице.",
             "lat": 55.7660, "lon": 37.6056},
        ],
    },
    {
        "title": "Каналы Санкт-Петербурга",
        "short_description": "Пешеходный маршрут вдоль каналов Санкт-Петербурга.",
        "full_description": "Знаменитые каналы и мосты Санкт-Петербурга.",
        "city": "Санкт-Петербург",
        "duration_minutes": 210,
        "price": 1800.0,
        "restrictions": "Маршрут зависит от погоды.",
        "points": [
            {"order": 1, "title": "Невский проспект",
             "description": "Старт на Невском проспекте.",
             "lat": 59.9343, "lon": 30.3351},
            {"order": 2, "title": "Канал Грибоедова",
             "description": "Прогулка вдоль канала.",
             "lat": 59.9311, "lon": 30.3286},
        ],
    },
    {
        "title": "Гастрономический день в Москве",
        "short_description": "Дневной маршрут по гастрономическим местам Москвы.",
        "full_description": "Длинный маршрут по нескольким районам с остановками в кафе и на рынках.",
        "city": "Москва",
        "duration_minutes": 330,
        "price": 3500.0,
        "restrictions": "Не подходит гостям с тяжёлыми пищевыми аллергиями.",
        "points": [
            {"order": 1, "title": "Даниловский рынок",
             "description": "Первая гастрономическая остановка.",
             "lat": 55.7102, "lon": 37.6293},
            {"order": 2, "title": "Патриаршие пруды",
             "description": "Кафе вокруг прудов.",
             "lat": 55.7639, "lon": 37.5919},
            {"order": 3, "title": "Арбат",
             "description": "Финальная остановка на Арбате.",
             "lat": 55.7494, "lon": 37.5912},
        ],
    },
]


SEED_NON_PUBLISHED_EXPERIENCES: list[dict] = [
    {
        "title": "Черновик: ночная Москва",
        "short_description": "Черновой маршрут по ночной Москве.",
        "full_description": "Черновик впечатления, ещё не опубликован.",
        "city": "Москва",
        "duration_minutes": 180,
        "price": 2000.0,
        "restrictions": "Только для совершеннолетних.",
        "status": ExperienceStatus.draft,
        "points": [
            {"order": 1, "title": "Площадь Революции",
             "description": "Старт ночного маршрута.",
             "lat": 55.7563, "lon": 37.6210},
            {"order": 2, "title": "Воробьёвы горы",
             "description": "Финальная смотровая площадка.",
             "lat": 55.7100, "lon": 37.5430},
        ],
    },
    {
        "title": "На модерации: парки Санкт-Петербурга",
        "short_description": "Маршрут по паркам, ожидает модерации.",
        "full_description": "Впечатление подано на модерацию.",
        "city": "Санкт-Петербург",
        "duration_minutes": 240,
        "price": 1700.0,
        "restrictions": "Сезонно: апрель–октябрь.",
        "status": ExperienceStatus.on_moderation,
        "points": [
            {"order": 1, "title": "Летний сад",
             "description": "Старт в Летнем саду.",
             "lat": 59.9450, "lon": 30.3367},
            {"order": 2, "title": "Михайловский сад",
             "description": "Вторая остановка.",
             "lat": 59.9402, "lon": 30.3360},
        ],
    },
]


def seed_users(db: Session) -> dict[str, User]:
    created: dict[str, User] = {}
    for data in SEED_USERS:
        user = db.query(User).filter(User.email == data["email"]).first()
        if user is None:
            user = User(
                email=data["email"],
                password_hash=hash_password(data["password"]),
                role=data["role"],
                status=UserStatus.active,
            )
            db.add(user)
            db.flush()
        created[data["email"]] = user
    return created


def _create_experience(db: Session, author: User, data: dict, default_status: ExperienceStatus) -> None:
    existing = (
        db.query(Experience)
        .filter(Experience.title == data["title"], Experience.city == data["city"])
        .first()
    )
    if existing is not None:
        return
    exp = Experience(
        author_id=author.id,
        title=data["title"],
        short_description=data["short_description"],
        full_description=data["full_description"],
        city=data["city"],
        duration_minutes=data["duration_minutes"],
        price=data["price"],
        restrictions=data["restrictions"],
        status=data.get("status", default_status),
    )
    db.add(exp)
    db.flush()
    for p in data["points"]:
        db.add(
            ExperiencePoint(
                experience_id=exp.id,
                order=p["order"],
                title=p["title"],
                description=p["description"],
                lat=p["lat"],
                lon=p["lon"],
            )
        )


def seed_experiences(db: Session, author: User) -> None:
    for data in SEED_EXPERIENCES:
        _create_experience(db, author, data, ExperienceStatus.published)
    for data in SEED_NON_PUBLISHED_EXPERIENCES:
        _create_experience(db, author, data, ExperienceStatus.draft)


def run_seed() -> None:
    # Создаём таблицы на случай, если Alembic ещё не применялся
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        users = seed_users(db)
        seed_experiences(db, users["author@test.com"])
        db.commit()
        print("Seed выполнен.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
