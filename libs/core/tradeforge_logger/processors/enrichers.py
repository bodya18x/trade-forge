# -*- coding: utf-8 -*-
"""Процессоры для обогащения логов метаданными.

Этот модуль содержит процессоры для добавления timestamp, log level, logger name,
service context и ContextVars контекста.
"""

from __future__ import annotations

import datetime
from typing import Any

from structlog.types import EventDict, WrappedLogger


def add_timestamp(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Добавляет ISO 8601 timestamp в UTC.

    Args:
        logger: Logger instance.
        method_name: Имя метода логирования.
        event_dict: Event dictionary.

    Returns:
        Обогащенный event_dict с полем timestamp.
    """
    event_dict["timestamp"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()
    return event_dict


def add_log_level(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Добавляет уровень логирования.

    Args:
        logger: Logger instance.
        method_name: Имя метода логирования (info, error, etc.).
        event_dict: Event dictionary.

    Returns:
        Обогащенный event_dict с полем level.
    """
    event_dict["level"] = method_name
    return event_dict


def add_logger_name(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Добавляет имя логгера.

    Args:
        logger: Logger instance.
        method_name: Имя метода логирования.
        event_dict: Event dictionary.

    Returns:
        Обогащенный event_dict с полем logger.
    """
    if hasattr(logger, "name"):
        event_dict["logger"] = logger.name
    return event_dict


def create_service_context_processor(
    service_name: str,
    version: str,
    environment: str,
    host: str,
    additional_context: dict[str, Any] | None = None,
):
    """Создает процессор для добавления контекста сервиса.

    Args:
        service_name: Имя сервиса.
        version: Версия сервиса.
        environment: Окружение.
        host: Имя хоста.
        additional_context: Дополнительные поля.

    Returns:
        Процессор функция.
    """
    static_context = {
        "service": service_name,
        "environment": environment,
        "host": host,
    }

    # Добавляем version только если он не "unknown"
    if version and version != "unknown":
        static_context["version"] = version

    if additional_context:
        static_context.update(additional_context)

    def processor(
        logger: WrappedLogger,
        method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        """Добавляет контекст сервиса в event_dict.

        Args:
            logger: Logger instance.
            method_name: Имя метода логирования.
            event_dict: Event dictionary.

        Returns:
            Обогащенный event_dict.
        """
        event_dict.update(static_context)
        return event_dict

    return processor


def add_contextvars_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Добавляет контекст из ContextVars (correlation_id, request_id, etc.).

    Args:
        logger: Logger instance.
        method_name: Имя метода логирования.
        event_dict: Event dictionary.

    Returns:
        Обогащенный event_dict с контекстом из ContextVars.
    """
    from ..context.manager import get_current_context

    context = get_current_context()

    if context:
        event_dict.update(context)

    return event_dict


def add_exception_info(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Добавляет структурированную информацию об исключении.

    Args:
        logger: Logger instance.
        method_name: Имя метода логирования.
        event_dict: Event dictionary.

    Returns:
        Обогащенный event_dict с информацией об исключении.
    """
    from ..utils import format_exception_info

    if "exc_info" in event_dict:
        exc_info = event_dict.pop("exc_info")

        if exc_info:
            if exc_info is True:
                exc_data = format_exception_info()
            else:
                exc_data = format_exception_info(exc_info)

            if exc_data:
                event_dict["exception"] = exc_data

    return event_dict


def add_caller_info(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Добавляет информацию о месте вызова (файл, строка, функция).

    ВНИМАНИЕ: Это замедляет работу, использовать только для отладки.

    Args:
        logger: Logger instance.
        method_name: Имя метода логирования.
        event_dict: Event dictionary.

    Returns:
        Обогащенный event_dict с caller info.
    """
    import inspect

    frame = inspect.currentframe()
    if frame is None:
        return event_dict

    try:
        caller_frame = frame
        for _ in range(10):
            caller_frame = caller_frame.f_back
            if caller_frame is None:
                break

            filename = caller_frame.f_code.co_filename
            if (
                "structlog" not in filename
                and "tradeforge_logger" not in filename
            ):
                event_dict["caller"] = {
                    "file": filename,
                    "line": caller_frame.f_lineno,
                    "function": caller_frame.f_code.co_name,
                }
                break
    finally:
        del frame

    return event_dict


def order_fields(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Упорядочивает поля в логе для лучшей читаемости.

    Приоритетные поля (timestamp, level, event) идут первыми.

    Args:
        logger: Logger instance.
        method_name: Имя метода логирования.
        event_dict: Event dictionary.

    Returns:
        Упорядоченный event_dict.
    """
    priority_fields = [
        "timestamp",
        "level",
        "event",
        "logger",
        "service",
        "version",
        "environment",
        "host",
        "correlation_id",
        "request_id",
        "trace_id",
        "span_id",
        "user_id",
    ]

    ordered: EventDict = {}

    for field in priority_fields:
        if field in event_dict:
            ordered[field] = event_dict[field]

    for key, value in event_dict.items():
        if key not in ordered:
            ordered[key] = value

    return ordered
