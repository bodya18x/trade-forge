"""
Модуль настройки observability для Internal API.

Включает:
- Структурированное логирование через tradeforge_logger
- Метрики Prometheus
- Трассировку OpenTelemetry (планируется)
"""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from tradeforge_logger import configure_logging, get_logger

from app.settings import settings

log = get_logger(__name__)


def setup_logging():
    """
    Настраивает структурированное логирование через tradeforge_logger.

    Использует unified систему логирования Trade Forge с поддержкой:
    - Correlation ID для distributed tracing
    - Request ID для каждого запроса
    - User ID для аудита
    - Автоматическая sanitization чувствительных данных
    """
    configure_logging(
        service_name=settings.SERVICE_NAME,
        environment=settings.ENVIRONMENT,
        log_level=settings.LOG_LEVEL,
        enable_json=True,
        enable_console_colors=False,
    )
    log.info(
        "logging.configured",
        service="internal-api",
        log_level=settings.LOG_LEVEL,
    )


def setup_metrics(app: FastAPI):
    """
    Настраивает экспорт метрик Prometheus.

    Добавляет стандартные метрики по HTTP-запросам:
    - http_request_duration_seconds
    - http_requests_total
    - http_request_size_bytes
    - http_response_size_bytes
    """
    Instrumentator().instrument(app).expose(app)
    log.info("metrics.configured", metrics_path="/metrics")


def setup_tracing(app: FastAPI):
    """
    Настраивает трассировку OpenTelemetry.

    TODO: Полная реализация с экспортерами должна быть потом реализована.
    Планируется интеграция с Jaeger/Tempo для distributed tracing.
    """
    log.debug("tracing.setup.called", status="not_implemented")
