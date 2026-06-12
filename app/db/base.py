# Импорт всех моделей, чтобы Alembic видел полную metadata
from app.db.base_class import Base  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.experience import Experience, ExperiencePoint  # noqa: F401
from app.models.route import PersonalRoute, RoutePoint  # noqa: F401
from app.models.journey import Journey, JourneyProgress  # noqa: F401
from app.models.order import Order, PurchaseAccess  # noqa: F401
from app.models.payment import PaymentWebhookEvent  # noqa: F401
from app.models.review import Review  # noqa: F401
from app.models.analytics import AnalyticsEvent  # noqa: F401
from app.models.moderation import ModerationDecision  # noqa: F401
from app.models.complaint import Complaint  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
