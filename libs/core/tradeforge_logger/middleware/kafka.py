# -*- coding: utf-8 -*-
"""Kafka middleware для логирования и контекста.

Этот модуль содержит middleware для Kafka consumer для установки контекста
из сообщений.
"""

from __future__ import annotations

from ..context import bind_context, generate_request_id

# Заголовок для correlation tracking в Kafka
CORRELATION_ID_KEY = "correlation_id"


class KafkaContextMiddleware:
    """Middleware для Kafka consumer для установки контекста из сообщения.

    Этот middleware извлекает correlation_id из заголовков Kafka сообщения
    и устанавливает его в контекст.

    Examples:
        >>> from tradeforge_logger.middleware import KafkaContextMiddleware
        >>> middleware = KafkaContextMiddleware()
        >>> # В Kafka consumer:
        >>> with middleware.context_from_message(message):
        ...     process_message(message)
    """

    def __init__(self, correlation_id_key: str = CORRELATION_ID_KEY):
        """Инициализация KafkaContextMiddleware.

        Args:
            correlation_id_key: Ключ для correlation_id в headers.
        """
        self.correlation_id_key = correlation_id_key

    def context_from_message(self, message: dict):
        """Создает контекст из Kafka сообщения.

        Args:
            message: Kafka сообщение (dict с полями headers, value, etc.).

        Returns:
            Context manager.

        Examples:
            >>> middleware = KafkaContextMiddleware()
            >>> message = {
            ...     "headers": {"correlation_id": "abc-123"},
            ...     "value": {...}
            ... }
            >>> with middleware.context_from_message(message):
            ...     logger.info("processing")  # будет содержать correlation_id
        """
        headers = message.get("headers", {})
        correlation_id = headers.get(self.correlation_id_key)

        request_id = generate_request_id()

        context_data = {"request_id": request_id}
        if correlation_id:
            context_data["correlation_id"] = correlation_id

        return bind_context(**context_data)
