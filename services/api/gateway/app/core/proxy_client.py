from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status
from tradeforge_logger import get_logger
from tradeforge_logger.context import get_correlation_id

from app.settings import settings

log = get_logger(__name__)


class InternalAPIClient:
    """
    HTTP клиент для проксирования запросов в Internal API.
    """

    def __init__(self):
        self.base_url = settings.INTERNAL_API_BASE_URL.rstrip("/")
        self.timeout = settings.INTERNAL_API_TIMEOUT
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "User-Agent": f"{settings.SERVICE_NAME}/{settings.SERVICE_VERSION}"
            },
        )

    async def close(self):
        """
        Закрывает HTTP клиент.
        """
        await self.client.aclose()

    async def forward_request(
        self,
        method: str,
        path: str,
        user_id: uuid.UUID,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """
        Проксирует HTTP запрос в Internal API.

        Args:
            method: HTTP метод (GET, POST, PUT, DELETE)
            path: Путь к эндпоинту (например, "/api/v1/strategies")
            user_id: UUID пользователя для добавления в заголовок X-User-ID
            params: Query параметры
            json_data: JSON данные для тела запроса
            headers: Дополнительные заголовки

        Returns:
            Ответ от Internal API

        Raises:
            HTTPException: При ошибках соединения или таймауте
        """
        # Подготавливаем заголовки
        request_headers = {
            "X-User-ID": str(user_id),
            "Content-Type": "application/json",
        }

        # Прокидываем correlation_id для трассировки запросов
        correlation_id = get_correlation_id()
        if correlation_id:
            request_headers["X-Correlation-ID"] = correlation_id

        if headers:
            request_headers.update(headers)

        try:
            log.debug(
                "internal.api.request.proxying",
                method=method,
                path=path,
                user_id=str(user_id),
            )

            response = await self.client.request(
                method=method.upper(),
                url=path,
                params=params,
                json=json_data,
                headers=request_headers,
            )

            log.debug(
                "internal.api.response.received",
                method=method,
                path=path,
                status_code=response.status_code,
                user_id=str(user_id),
            )

            return response

        except httpx.TimeoutException as e:
            log.error(
                "internal.api.timeout",
                method=method,
                path=path,
                user_id=str(user_id),
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Internal API request timed out",
            )

        except httpx.ConnectError as e:
            log.error(
                "internal.api.connection.error",
                method=method,
                path=path,
                user_id=str(user_id),
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Internal API is unavailable",
            )

        except httpx.HTTPStatusError as e:
            log.error(
                "internal.api.http.error",
                method=method,
                path=path,
                user_id=str(user_id),
                status_code=e.response.status_code,
                error=str(e),
            )
            # Проксируем HTTP ошибки как есть
            raise HTTPException(
                status_code=e.response.status_code,
                detail=e.response.text or "Internal API error",
            )

        except Exception as e:
            log.error(
                "internal.api.error.unexpected",
                method=method,
                path=path,
                user_id=str(user_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unexpected error occurred while processing request",
            )

    async def get(
        self,
        path: str,
        user_id: uuid.UUID,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        Выполняет GET запрос к Internal API.
        """
        return await self.forward_request("GET", path, user_id, params=params)

    async def post(
        self,
        path: str,
        user_id: uuid.UUID,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        Выполняет POST запрос к Internal API.
        """
        return await self.forward_request(
            "POST", path, user_id, params=params, json_data=json_data
        )

    async def put(
        self,
        path: str,
        user_id: uuid.UUID,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        Выполняет PUT запрос к Internal API.
        """
        return await self.forward_request(
            "PUT", path, user_id, json_data=json_data
        )

    async def delete(
        self,
        path: str,
        user_id: uuid.UUID,
    ) -> httpx.Response:
        """
        Выполняет DELETE запрос к Internal API.
        """
        return await self.forward_request("DELETE", path, user_id)


# Глобальный экземпляр клиента
internal_api_client = InternalAPIClient()
