# -*- coding: utf-8 -*-
"""Trade Forge Logger - унифицированная система логирования для микросервисов.

Эта библиотека предоставляет production-ready решение для структурированного
логирования в микросервисной архитектуре Trade Forge.

Основные возможности:
- Структурированное логирование на базе structlog
- Автоматический контекст (correlation_id, request_id, user_id)
- Sanitization чувствительных данных
- JSON и Console форматтеры
- FastAPI middleware для автоматического логирования HTTP запросов
- Интеграция с OpenTelemetry (опционально)

Quick Start:
    >>> from tradeforge_logger import configure_logging, get_logger
    >>> # В main.py сервиса:
    >>> configure_logging(
    ...     service_name="order-service",
    ...     environment="production",
    ...     log_level="INFO",
    ... )
    >>> # В любом модуле:
    >>> logger = get_logger(__name__)
    >>> logger.info("order_created", order_id="ORD-123", amount=100.50)

FastAPI Integration:
    >>> from fastapi import FastAPI
    >>> from tradeforge_logger.middleware import (
    ...     RequestContextMiddleware,
    ...     LoggingMiddleware,
    ... )
    >>> app = FastAPI()
    >>> app.add_middleware(RequestContextMiddleware)
    >>> app.add_middleware(LoggingMiddleware)

Context Management:
    >>> from tradeforge_logger import bind_context, get_logger
    >>> logger = get_logger(__name__)
    >>> with bind_context(transaction_id="tx_123", user_id="user_456"):
    ...     logger.info("transaction_started")  # содержит tx_id и user_id
    ...     logger.info("transaction_completed")
"""

from __future__ import annotations

from .config import LoggerConfig
from .context import (
    bind_context,
    clear_all_context,
    generate_request_id,
    get_correlation_id,
    get_current_context,
    get_custom_context,
    get_request_id,
    get_user_id,
    set_correlation_id,
    set_custom_context,
    set_request_id,
    set_user_id,
)
from .logger import configure_logging, get_config, get_logger, is_configured

__version__ = "1.0.0"

__all__ = [
    # Версия
    "__version__",
    # Конфигурация
    "LoggerConfig",
    "configure_logging",
    "get_config",
    "is_configured",
    # Core API
    "get_logger",
    # Context Management
    "bind_context",
    "get_current_context",
    "clear_all_context",
    # Correlation ID
    "set_correlation_id",
    "get_correlation_id",
    # Request ID
    "set_request_id",
    "get_request_id",
    "generate_request_id",
    # User ID
    "set_user_id",
    "get_user_id",
    # Custom Context
    "set_custom_context",
    "get_custom_context",
]
