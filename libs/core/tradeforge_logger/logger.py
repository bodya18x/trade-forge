# -*- coding: utf-8 -*-
"""Ядро системы логирования Trade Forge.

Этот модуль содержит главные функции для конфигурации и получения логгеров.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.typing import FilteringBoundLogger

from .config import LoggerConfig
from .formatters import get_formatter
from .processors import (
    add_caller_info,
    add_contextvars_context,
    add_exception_info,
    add_log_level,
    add_logger_name,
    add_timestamp,
    create_sanitizer_processor,
    create_service_context_processor,
    create_tracing_processor,
    order_fields,
)

# Глобальное хранилище конфигурации
_global_config: LoggerConfig | None = None
_is_configured: bool = False
_is_default_config: bool = False  # Флаг что применена базовая конфигурация


def _apply_default_config() -> None:
    """Применяет минимальную базовую конфигурацию логирования.

    Вызывается автоматически при первом get_logger() если configure_logging()
    не был вызван явно. Позволяет использовать логгер без предварительной настройки.
    """
    global _global_config, _is_configured, _is_default_config

    # Создаем минимальную конфигурацию
    default_config = LoggerConfig(
        service_name="unknown-service",
        environment="development",
        log_level="INFO",
        enable_json=True,
        enable_console_colors=False,
    )

    _global_config = default_config

    # Конфигурируем stdlib logging
    _configure_stdlib_logging(default_config)

    # Конфигурируем structlog
    _configure_structlog(default_config)

    _is_configured = True
    _is_default_config = True


def configure_logging(
    config: LoggerConfig | None = None,
    **kwargs: Any,
) -> None:
    """Глобальная конфигурация системы логирования.

    Эта функция должна вызываться один раз при старте приложения (в main.py).
    Если не вызвана, при первом get_logger() будет применена базовая конфигурация.

    Args:
        config: Объект LoggerConfig или None для создания из kwargs.
        **kwargs: Параметры для создания LoggerConfig если config=None.

    Examples:
        >>> from tradeforge_logger import configure_logging, LoggerConfig
        >>> config = LoggerConfig(
        ...     service_name="order-service",
        ...     environment="production",
        ...     log_level="INFO",
        ... )
        >>> configure_logging(config)

        Или:
        >>> configure_logging(
        ...     service_name="order-service",
        ...     environment="production",
        ...     log_level="INFO",
        ... )

    Raises:
        RuntimeError: Если логирование уже было сконфигурировано явно
            (не базовой конфигурацией).
    """
    global _global_config, _is_configured, _is_default_config

    # Разрешаем переконфигурацию если применена только базовая конфигурация
    if _is_configured and not _is_default_config:
        raise RuntimeError(
            "Logging уже был сконфигурирован. "
            "configure_logging() должен вызываться только один раз."
        )

    # Если была базовая конфигурация - сбрасываем её
    if _is_default_config:
        structlog.reset_defaults()

    # Создаем конфигурацию если не передана
    if config is None:
        config = LoggerConfig(**kwargs)

    _global_config = config

    # Конфигурируем stdlib logging
    _configure_stdlib_logging(config)

    # Конфигурируем structlog
    _configure_structlog(config)

    _is_configured = True
    _is_default_config = False  # Явная конфигурация


def _configure_stdlib_logging(config: LoggerConfig) -> None:
    """Конфигурирует стандартный logging модуль.

    Args:
        config: Конфигурация логгера.
    """
    # Устанавливаем уровень логирования для root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=config.log_level,
    )

    # Отключаем verbose логи от сторонних библиотек
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def _configure_structlog(config: LoggerConfig) -> None:
    """Конфигурирует structlog.

    Args:
        config: Конфигурация логгера.
    """
    # Создаем процессоры
    processors: list[Any] = [
        # 1. Добавляем уровень логирования
        add_log_level,
        # 2. Добавляем timestamp
        add_timestamp,
        # 3. Добавляем имя логгера
        add_logger_name,
        # 4. Добавляем контекст сервиса (service, version, environment, host)
        create_service_context_processor(
            service_name=config.service_name,
            version=config.version,
            environment=config.environment,
            host=config.host,
            additional_context=config.additional_context,
        ),
        # 5. Добавляем контекст из ContextVars (correlation_id, request_id, etc.)
        add_contextvars_context,
        # 6. Добавляем tracing информацию (trace_id, span_id)
        create_tracing_processor(config.enable_tracing),
        # 7. Обрабатываем исключения
        add_exception_info,
        # 8. Sanitize чувствительные данные
        create_sanitizer_processor(config.sanitize_fields),
        # 9. Добавляем caller info (опционально, замедляет работу)
        *([add_caller_info] if config.add_caller_info else []),
        # 10. Упорядочиваем поля
        order_fields,
        # 11. Форматируем в JSON или Console
        structlog.processors.ExceptionRenderer(),  # Для exception rendering
        get_formatter(
            enable_json=config.enable_json,
            enable_colors=config.enable_console_colors,
        ),
    ]

    # Конфигурируем structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(config.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """Получить сконфигурированный логгер.

    Если configure_logging() не был вызван явно, автоматически применяется
    базовая конфигурация при первом вызове get_logger().

    Args:
        name: Имя логгера (обычно __name__ модуля). Если None, используется
            "root".

    Returns:
        Сконфигурированный structlog logger.

    Examples:
        >>> from tradeforge_logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("order_created", order_id="ORD-123", amount=100.50)
    """
    # Автоматически применяем базовую конфигурацию если не сконфигурировано
    if not _is_configured:
        _apply_default_config()

    if name is None:
        name = "root"

    return structlog.get_logger(name)


def get_config() -> LoggerConfig:
    """Получить текущую конфигурацию логирования.

    Returns:
        Текущая конфигурация.

    Raises:
        RuntimeError: Если логирование не было сконфигурировано.
    """
    if _global_config is None:
        raise RuntimeError(
            "Logging не сконфигурирован. "
            "Сначала вызовите configure_logging()."
        )

    return _global_config


def is_configured() -> bool:
    """Проверить, было ли логирование сконфигурировано.

    Returns:
        True если configure_logging() был вызван.
    """
    return _is_configured


def reset_configuration() -> None:
    """Сбросить конфигурацию логирования.

    ВНИМАНИЕ: Используется только для тестов!
    """
    global _global_config, _is_configured, _is_default_config
    _global_config = None
    _is_configured = False
    _is_default_config = False
    structlog.reset_defaults()
