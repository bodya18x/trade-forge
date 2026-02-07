# -*- coding: utf-8 -*-
"""Процессоры и утилиты для sanitization чувствительных данных.

Этот модуль содержит функции для маскировки чувствительных данных в логах.
"""

from __future__ import annotations

from typing import Any

from structlog.types import EventDict, WrappedLogger

REDACTED_PLACEHOLDER = "[REDACTED]"


def sanitize_value(
    value: Any,
    sensitive_fields: set[str],
) -> Any:
    """Рекурсивно маскирует чувствительные поля.

    Args:
        value: Значение для обработки.
        sensitive_fields: Set чувствительных полей (lowercase).

    Returns:
        Обработанное значение с замаскированными чувствительными полями.

    Examples:
        >>> sensitive = {"password", "token"}
        >>> sanitize_value({"password": "secret"}, sensitive)
        {'password': '[REDACTED]'}
        >>> sanitize_value({"user": {"token": "abc"}}, sensitive)
        {'user': {'token': '[REDACTED]'}}
    """
    if isinstance(value, dict):
        return {
            key: (
                REDACTED_PLACEHOLDER
                if key.lower() in sensitive_fields
                else sanitize_value(val, sensitive_fields)
            )
            for key, val in value.items()
        }
    elif isinstance(value, (list, tuple)):
        return type(value)(
            sanitize_value(item, sensitive_fields) for item in value
        )
    else:
        return value


def create_sanitizer(sensitive_fields: list[str]):
    """Создает функцию sanitization с закешированным set.

    Args:
        sensitive_fields: Список чувствительных полей.

    Returns:
        Функция для sanitization.

    Examples:
        >>> sanitizer = create_sanitizer(["password", "token"])
        >>> sanitizer({"password": "secret", "username": "john"})
        {'password': '[REDACTED]', 'username': 'john'}
    """
    sensitive_set = set(field.lower() for field in sensitive_fields)

    def sanitizer(data: Any) -> Any:
        """Sanitize data.

        Args:
            data: Данные для обработки.

        Returns:
            Обработанные данные.
        """
        return sanitize_value(data, sensitive_set)

    return sanitizer


def create_sanitizer_processor(sensitive_fields: list[str]):
    """Создает процессор для sanitization чувствительных данных.

    Args:
        sensitive_fields: Список чувствительных полей.

    Returns:
        Процессор функция.
    """
    sanitizer = create_sanitizer(sensitive_fields)

    def processor(
        logger: WrappedLogger,
        method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        """Маскирует чувствительные данные в event_dict.

        Args:
            logger: Logger instance.
            method_name: Имя метода логирования.
            event_dict: Event dictionary.

        Returns:
            Обогащенный event_dict с замаскированными данными.
        """
        return sanitizer(event_dict)

    return processor
