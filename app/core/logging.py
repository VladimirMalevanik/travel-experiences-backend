import logging
import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("app.request")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "method=%s path=%s status_code=500 latency_ms=%.2f",
                request.method,
                request.url.path,
                latency_ms,
            )
            raise
        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "method=%s path=%s status_code=%s latency_ms=%.2f",
            request.method,
            request.url.path,
            status_code,
            latency_ms,
        )
        return response
