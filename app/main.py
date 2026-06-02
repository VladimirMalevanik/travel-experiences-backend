from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.catalog import router as catalog_router
from app.api.experiences import router as experiences_router
from app.api.journeys import router as journeys_router
from app.api.me import router as me_router
from app.api.orders import router as orders_router
from app.api.payments import router as payments_router
from app.api.purchases import router as purchases_router
from app.api.routes import router as routes_router
from app.core.config import settings
from app.core.logging import RequestLoggingMiddleware, configure_logging

configure_logging()

app = FastAPI(
    title="Travel Experiences Backend",
    description=(
        "Backend трэвел-приложения «впечатлений»: каталог впечатлений, "
        "покупка, сопровождение прохождения и личные маршруты."
    ),
    version="0.1.0",
    debug=settings.DEBUG,
)

app.add_middleware(RequestLoggingMiddleware)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(me_router)
app.include_router(catalog_router)
app.include_router(experiences_router)
app.include_router(routes_router)
app.include_router(journeys_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(purchases_router)
