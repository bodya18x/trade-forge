"""
Сервис бэктестов - Бизнес-логика для операций с бэктестами.
Валидирует, преобразует и обогащает запросы бэктестов перед проксированием во внутренний API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from redis.asyncio import Redis
from tradeforge_logger import get_logger

from app.core.internal_api_utils import extract_error_detail_safe
from app.core.proxy_client import InternalAPIClient
from app.core.rate_limiting import check_user_rate_limits
from app.settings import settings

log = get_logger(__name__)


class BacktestService:
    """
    Сервис бизнес-логики для операций с бэктестами.

    Этот сервис добавляет корректную валидацию, ограничение скорости и бизнес-логику
    поверх вызовов внутреннего API вместо слепого проксирования.
    """

    def __init__(self, redis: Redis, internal_client: InternalAPIClient):
        self.redis = redis
        self.internal_client = internal_client

    def _validate_date_range_for_tier(
        self, start_date: str, end_date: str, subscription_tier: str
    ) -> None:
        """
        Валидирует диапазон дат по тарифному плану.

        Args:
            start_date: Дата начала (ISO формат)
            end_date: Дата окончания (ISO формат)
            subscription_tier: Тарифный план пользователя

        Raises:
            HTTPException: При превышении максимального периода для тарифа
        """
        tier_limits = settings.SUBSCRIPTION_LIMITS.get(
            subscription_tier, settings.SUBSCRIPTION_LIMITS["free"]
        )
        max_years = tier_limits["backtest_max_years"]

        try:
            # Парсинг дат (поддерживаем оба формата)
            if "T" in start_date:
                parsed_start = datetime.fromisoformat(
                    start_date.replace("Z", "+00:00")
                )
            else:
                parsed_start = datetime.fromisoformat(
                    start_date + "T00:00:00+00:00"
                )

            if "T" in end_date:
                parsed_end = datetime.fromisoformat(
                    end_date.replace("Z", "+00:00")
                )
            else:
                parsed_end = datetime.fromisoformat(
                    end_date + "T23:59:59+00:00"
                )

            # Проверяем период
            period_days = (parsed_end - parsed_start).days
            max_days = max_years * 365

            if period_days > max_days:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Период тестирования ({period_days} дней) превышает максимально допустимый "
                    f"для тарифа '{subscription_tier}' ({max_years} {'год' if max_years == 1 else 'лет'}, {max_days} дней)",
                )

        except ValueError as e:
            # Ошибки парсинга дат будут обработаны в Internal API
            log.debug(
                "backtest.date.parse.error",
                start_date=start_date,
                end_date=end_date,
                error=str(e),
            )

    async def create_backtest(
        self,
        user_id: uuid.UUID,
        strategy_id: uuid.UUID,
        ticker: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        simulation_params: Dict[str, Any],
        subscription_tier: str = "free",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Создает новый бэктест с корректной валидацией и ограничением скорости.

        Args:
            user_id: UUID пользователя
            strategy_id: UUID стратегии
            ticker: Тикер инструмента
            timeframe: Таймфрейм (например, "1h", "1d")
            start_date: Дата начала
            end_date: Дата окончания
            simulation_params: Параметры симуляции
            subscription_tier: Тарифный план для валидации лимитов
            idempotency_key: Опциональный ключ идемпотентности

        Returns:
            Данные созданной задачи бэктеста

        Raises:
            HTTPException: При ошибках создания
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(
                redis=self.redis,
                user_id=user_id,
                method="POST",
                subscription_tier=subscription_tier,
                resource_type="backtest",
            )

            # Валидируем диапазон дат согласно лимитам тарифного плана
            self._validate_date_range_for_tier(
                start_date, end_date, subscription_tier
            )

            # Формируем данные запроса - бизнес-валидация не выполняется в Gateway
            backtest_data = {
                "strategy_id": str(strategy_id),
                "ticker": ticker.strip().upper() if ticker else ticker,
                "timeframe": timeframe,
                "start_date": start_date,
                "end_date": end_date,
                "simulation_params": simulation_params,
            }

            # Настраиваем заголовки для идемпотентности
            headers = {}
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key

            # Создаем бэктест через внутренний API (вся валидация происходит там)
            response = await self.internal_client.forward_request(
                method="POST",
                path="/api/v1/backtests/",
                user_id=user_id,
                json_data=backtest_data,
                headers=headers,
            )

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Strategy not found or access denied",
                )
            elif response.status_code != 201:
                # Извлекаем безопасное сообщение об ошибке из ответа Internal API
                detail = extract_error_detail_safe(
                    response.text, "Backtest creation failed"
                )
                raise HTTPException(
                    status_code=response.status_code, detail=detail
                )

            job_data = response.json()

            log.info(
                "backtest.created",
                user_id=str(user_id),
                job_id=job_data.get("id"),
                strategy_id=str(strategy_id),
                ticker=backtest_data["ticker"],
                timeframe=timeframe,
            )

            return job_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "backtest.creation.failed",
                user_id=str(user_id),
                strategy_id=str(strategy_id),
                ticker=str(ticker),
                timeframe=timeframe,
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Backtest creation service error",
            )

    async def get_backtest(
        self, user_id: uuid.UUID, job_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Получает статус и результаты бэктеста с валидацией.

        Args:
            user_id: UUID пользователя
            job_id: UUID задачи бэктеста

        Returns:
            Данные задачи бэктеста с результатами
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(self.redis, user_id, "GET")

            # Получаем бэктест из внутреннего API
            response = await self.internal_client.get(
                path=f"/api/v1/backtests/{job_id}", user_id=user_id
            )

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Backtest not found or access denied",
                )
            elif response.status_code != 200:
                # Извлекаем безопасное сообщение об ошибке
                detail = extract_error_detail_safe(
                    response.text, "Failed to retrieve backtest"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            backtest_data = response.json()

            log.info(
                "backtest.retrieved",
                user_id=str(user_id),
                job_id=str(job_id),
                status=backtest_data.get("job", {}).get("status", "unknown"),
            )

            return backtest_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "backtest.retrieval.failed",
                user_id=str(user_id),
                job_id=str(job_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Backtest retrieval service error",
            )

    async def get_user_backtests(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        strategy_id: uuid.UUID | None = None,
        sort_by: str = "created_at",
        sort_direction: str = "desc",
    ) -> Dict[str, Any]:
        """
        Получает бэктесты пользователя с валидацией и ограничением скорости.

        Args:
            user_id: UUID пользователя
            limit: Количество бэктестов для возврата
            offset: Смещение для пагинации
            strategy_id: Опциональный UUID стратегии для фильтрации
            sort_by: Поле для сортировки
            sort_direction: Направление сортировки (asc/desc)

        Returns:
            Пагинированный список бэктестов
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(self.redis, user_id, "GET")

            # Подготавливаем параметры
            params = {
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_direction": sort_direction,
            }
            if strategy_id:
                params["strategy_id"] = str(strategy_id)

            # Получаем бэктесты из внутреннего API (валидация пагинации происходит там)
            response = await self.internal_client.get(
                path="/api/v1/backtests/",
                user_id=user_id,
                params=params,
            )

            if response.status_code != 200:
                # Извлекаем безопасное сообщение об ошибке
                detail = extract_error_detail_safe(
                    response.text, "Failed to retrieve backtests"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            backtests_data = response.json()

            log.info(
                "backtests.list.retrieved",
                user_id=str(user_id),
                strategy_id=str(strategy_id) if strategy_id else None,
                count=len(backtests_data.get("items", [])),
                total=backtests_data.get("total", 0),
            )

            return backtests_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "backtests.list.retrieval.failed",
                user_id=str(user_id),
                strategy_id=str(strategy_id) if strategy_id else None,
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Backtest retrieval service error",
            )
