# -*- coding: utf-8 -*-
"""FastAPI middleware для логирования и контекста.

Этот модуль содержит middleware для автоматического логирования HTTP запросов
и управления контекстом (correlation_id, request_id).
"""

from __future__ import annotations

import uuid
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..context import (
    clear_all_context,
    generate_request_id,
    set_correlation_id,
    set_request_id,
)
from ..logger import get_logger

# Заголовки для correlation tracking
CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware для извлечения и установки контекста запроса.

    Этот middleware должен быть первым в цепочке middleware.

    Он:
    1. Генерирует request_id для каждого запроса
    2. Извлекает correlation_id из заголовка X-Correlation-ID
    3. Сохраняет их в ContextVars
    4. Добавляет request_id в response headers
    5. Очищает контекст после обработки запроса

    Examples:
        >>> from fastapi import FastAPI
        >>> from tradeforge_logger.middleware import RequestContextMiddleware
        >>> app = FastAPI()
        >>> app.add_middleware(RequestContextMiddleware)
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Обработка запроса.

        Args:
            request: HTTP запрос.
            call_next: Следующий обработчик в цепочке.

        Returns:
            HTTP ответ.
        """
        # Генерируем request_id
        request_id = generate_request_id()
        set_request_id(request_id)

        # Извлекаем correlation_id из заголовка
        correlation_id = request.headers.get(CORRELATION_ID_HEADER)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        set_correlation_id(correlation_id)

        try:
            # Обрабатываем запрос
            response = await call_next(request)

            # Добавляем request_id в response headers
            response.headers[REQUEST_ID_HEADER] = request_id

            # Пробрасываем correlation_id если был
            if correlation_id:
                response.headers[CORRELATION_ID_HEADER] = correlation_id

            return response
        finally:
            # Очищаем контекст после завершения запроса
            clear_all_context()


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для автоматического логирования HTTP запросов.

    Этот middleware:
    1. Логирует входящие запросы (method, path, headers)
    2. Логирует исходящие ответы (status_code, duration_ms)
    3. Логирует исключения с контекстом
    4. Измеряет время обработки запроса

    ВАЖНО: Этот middleware должен идти ПОСЛЕ RequestContextMiddleware,
    чтобы иметь доступ к correlation_id и request_id.

    Examples:
        >>> from fastapi import FastAPI
        >>> from tradeforge_logger.middleware import (
        ...     RequestContextMiddleware,
        ...     LoggingMiddleware,
        ... )
        >>> app = FastAPI()
        >>> app.add_middleware(RequestContextMiddleware)
        >>> app.add_middleware(LoggingMiddleware)
    """

    def __init__(
        self,
        app,
        *,
        skip_paths: list[str] | None = None,
        log_request_body: bool = False,
        log_response_body: bool = False,
    ):
        """Инициализация LoggingMiddleware.

        Args:
            app: ASGI приложение.
            skip_paths: Список путей для пропуска логирования (например,
                health checks).
            log_request_body: Логировать ли тело запроса (осторожно с
                чувствительными данными).
            log_response_body: Логировать ли тело ответа.
        """
        super().__init__(app)
        self.skip_paths = skip_paths or ["/health", "/healthz", "/metrics"]
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.logger = get_logger(__name__)

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Обработка запроса с логированием.

        Args:
            request: HTTP запрос.
            call_next: Следующий обработчик в цепочке.

        Returns:
            HTTP ответ.
        """
        # Проверяем, нужно ли пропустить логирование
        if request.url.path in self.skip_paths:
            return await call_next(request)

        # Извлекаем информацию о запросе
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params)
        client_host = request.client.host if request.client else None

        # Логируем входящий запрос
        log_data = {
            "method": method,
            "path": path,
            "client_host": client_host,
        }

        if query_params:
            log_data["query_params"] = query_params

        self.logger.info("http_request_received", **log_data)

        # Измеряем время обработки
        start_time = time.perf_counter()

        try:
            # Обрабатываем запрос
            response = await call_next(request)

            # Вычисляем длительность
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Логируем успешный ответ
            self.logger.info(
                "http_request_completed",
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            return response

        except Exception as exc:
            # Вычисляем длительность
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Логируем ошибку с контекстом
            self.logger.error(
                "http_request_failed",
                method=method,
                path=path,
                duration_ms=round(duration_ms, 2),
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
            )

            # Пробрасываем исключение дальше
            raise
