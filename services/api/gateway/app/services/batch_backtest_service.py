"""
Сервис групповых бэктестов для Gateway API - проверяет rate limits и проксирует во внутренний API.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import HTTPException, status
from redis.asyncio import Redis
from tradeforge_logger import get_logger

from app.core.internal_api_utils import extract_error_detail_safe
from app.core.proxy_client import InternalAPIClient
from app.core.rate_limiting import RateLimiter, check_user_rate_limits
from app.services.backtest_service import BacktestService

log = get_logger(__name__)


class BatchBacktestService:
    """
    Сервис для работы с групповыми бэктестами в Gateway API.

    Отвечает за проверку rate limits и проксирование запросов во внутренний API.
    """

    def __init__(self, redis: Redis, internal_client: InternalAPIClient):
        self.redis = redis
        self.internal_client = internal_client
        self.rate_limiter = RateLimiter(redis)

    async def create_batch_backtests(
        self,
        user_id: uuid.UUID,
        description: str,
        backtests: list[Dict[str, Any]],
        subscription_tier: str = "free",
        idempotency_key: str | None = None,
    ) -> Dict[str, Any]:
        """
        Создает групповой бэктест с проверкой rate limits.

        Args:
            user_id: ID пользователя
            description: Описание группы
            backtests: Список параметров бэктестов
            subscription_tier: Тарифный план пользователя
            idempotency_key: Ключ идемпотентности

        Returns:
            Данные созданного группового бэктеста

        Raises:
            HTTPException: При превышении лимитов или ошибках
        """
        try:
            batch_size = len(backtests)

            # Проверяем максимальный размер batch (не более 50)
            if batch_size > 50:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Максимальный размер batch: 50 бэктестов. Запрошено: {batch_size}",
                )

            await check_user_rate_limits(
                redis=self.redis,
                user_id=user_id,
                method="POST",
                subscription_tier=subscription_tier,
                resource_type="backtest",
            )

            # Проверяем диапазон дат для каждого бэктеста по тарифному плану
            self._validate_batch_date_ranges(backtests, subscription_tier)

            # Проверяем лимиты на batch
            await self._check_batch_limits(
                user_id, batch_size, subscription_tier
            )

            # Строим запрос для Internal API
            batch_request = {
                "description": description,
                "backtests": backtests,
            }

            # Устанавливаем заголовки
            headers = {}
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key

            # Отправляем запрос во внутренний API
            response = await self.internal_client.forward_request(
                method="POST",
                path="/api/v1/backtests/batch",
                user_id=user_id,
                json_data=batch_request,
                headers=headers,
            )

            if response.status_code == 422:
                # Извлекаем детали валидационных ошибок
                detail = extract_error_detail_safe(
                    response.text, "Invalid batch backtest parameters"
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=detail,
                )
            elif response.status_code != 201:
                # Обрабатываем другие ошибки от Internal API
                detail = extract_error_detail_safe(
                    response.text, "Batch backtest creation failed"
                )
                raise HTTPException(
                    status_code=response.status_code, detail=detail
                )

            batch_data = response.json()

            log.info(
                "batch.backtest.created",
                user_id=str(user_id),
                batch_id=batch_data.get("batch_id"),
                total_count=batch_size,
                description=description,
            )

            return batch_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "batch.backtest.creation.failed",
                user_id=str(user_id),
                batch_size=batch_size,
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Batch backtest creation service error",
            )

    async def get_batch_status(
        self, user_id: uuid.UUID, batch_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Получает статус группового бэктеста.

        Args:
            user_id: ID пользователя
            batch_id: ID группового бэктеста

        Returns:
            Данные группового бэктеста

        Raises:
            HTTPException: При ошибках или если batch не найден
        """
        try:
            # Проверяем общие rate limits
            await self.rate_limiter.check_user_rate_limit(
                user_id, "general", "free"
            )

            # Получаем данные от Internal API
            response = await self.internal_client.get(
                path=f"/api/v1/backtests/batch/{batch_id}",
                user_id=user_id,
            )

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Batch backtest not found or access denied",
                )
            elif response.status_code != 200:
                detail = extract_error_detail_safe(
                    response.text, "Failed to retrieve batch backtest"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            batch_data = response.json()

            log.info(
                "batch.backtest.status.retrieved",
                user_id=str(user_id),
                batch_id=str(batch_id),
                status=batch_data.get("status", "unknown"),
            )

            return batch_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "batch.backtest.status.retrieval.failed",
                user_id=str(user_id),
                batch_id=str(batch_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Batch backtest retrieval service error",
            )

    async def get_user_batch_backtests(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        status_filter: str | None = None,
        sort_by: str = "created_at",
        sort_direction: str = "desc",
    ) -> Dict[str, Any]:
        """
        Получает список групповых бэктестов пользователя.

        Args:
            user_id: ID пользователя
            limit: Количество записей
            offset: Смещение
            status_filter: Фильтр по статусу
            sort_by: Поле сортировки
            sort_direction: Направление сортировки

        Returns:
            Пагинированный список групповых бэктестов
        """
        try:
            # Проверяем общие rate limits
            await self.rate_limiter.check_user_rate_limit(
                user_id, "general", "free"
            )

            # Подготавливаем параметры
            params = {
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_direction": sort_direction,
            }
            if status_filter:
                params["status_filter"] = status_filter

            # Получаем данные от Internal API
            response = await self.internal_client.get(
                path="/api/v1/backtests/batch",
                user_id=user_id,
                params=params,
            )

            if response.status_code != 200:
                detail = extract_error_detail_safe(
                    response.text, "Failed to retrieve batch backtests"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            batch_list = response.json()

            log.info(
                "batch.backtests.list.retrieved",
                user_id=str(user_id),
                count=len(batch_list.get("items", [])),
                total=batch_list.get("total", 0),
            )

            return batch_list

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "batch.backtests.list.retrieval.failed",
                user_id=str(user_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Batch backtest list retrieval service error",
            )

    async def _check_batch_limits(
        self, user_id: uuid.UUID, batch_size: int, subscription_tier: str
    ) -> None:
        """
        Проверяет лимиты для группового бэктеста.

        Args:
            user_id: ID пользователя
            batch_size: Размер группы
            subscription_tier: Тарифный план

        Raises:
            HTTPException: При превышении лимитов
        """
        # Проверяем дневной лимит на количество бэктестов
        daily_remaining = await self._get_daily_backtests_remaining(
            user_id, subscription_tier
        )

        if batch_size > daily_remaining:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Недостаточно дневного лимита бэктестов. "
                f"Запрошено: {batch_size}, доступно: {daily_remaining}",
            )

        # # Проверяем лимит одновременных бэктестов
        # concurrent_remaining = await self._get_concurrent_backtests_remaining(
        #     user_id, subscription_tier
        # )

        # if batch_size > concurrent_remaining:
        #     raise HTTPException(
        #         status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        #         detail=f"Недостаточно лимита одновременных бэктестов. "
        #         f"Запрошено: {batch_size}, доступно: {concurrent_remaining}",
        #     )

    async def _get_daily_backtests_remaining(
        self, user_id: uuid.UUID, subscription_tier: str
    ) -> int:
        """Получает оставшееся количество дневных бэктестов."""
        try:
            limits_info = await self.rate_limiter.check_resource_limit(
                user_id, "backtests", "daily", subscription_tier
            )
            return limits_info["remaining"]
        except Exception:
            # В случае ошибки Redis - разрешаем операцию
            return 9999

    async def _get_concurrent_backtests_remaining(
        self, user_id: uuid.UUID, subscription_tier: str
    ) -> int:
        """Получает оставшееся количество одновременных бэктестов."""
        try:
            limits_info = await self.rate_limiter.check_resource_limit(
                user_id, "backtests", "concurrent", subscription_tier
            )
            return limits_info["remaining"]
        except Exception:
            # В случае ошибки Redis - разрешаем операцию
            return 9999

    def _validate_batch_date_ranges(
        self, backtests: list[Dict[str, Any]], subscription_tier: str
    ) -> None:
        """
        Валидирует диапазоны дат для всех бэктестов в batch по тарифному плану.
        Использует ту же логику, что и для одиночных бэктестов.

        Args:
            backtests: Список параметров бэктестов
            subscription_tier: Тарифный план пользователя

        Raises:
            HTTPException: При превышении максимального периода для тарифа
        """
        # Создаем временный экземпляр для использования метода валидации
        temp_service = BacktestService(self.redis, self.internal_client)

        for idx, backtest in enumerate(backtests):
            start_date_str = backtest.get("start_date")
            end_date_str = backtest.get("end_date")
            ticker = backtest.get("ticker", "UNKNOWN")

            if not start_date_str or not end_date_str:
                continue  # Будет проверено в Internal API

            try:
                # Используем общий метод валидации из BacktestService
                temp_service._validate_date_range_for_tier(
                    start_date_str, end_date_str, subscription_tier
                )
            except HTTPException as e:
                # Обогащаем ошибку информацией о номере бэктеста
                raise HTTPException(
                    status_code=e.status_code,
                    detail=f"Бэктест #{idx + 1} (ticker: {ticker}): {e.detail}",
                )
