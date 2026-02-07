"""
Middleware и утилиты ограничения скорости для Gateway API.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from tradeforge_logger import get_logger
from tradeforge_schemas import ErrorResponse

from app.settings import settings

log = get_logger(__name__)


class RateLimitExceeded(Exception):
    """Исключение превышения лимита скорости."""

    def __init__(
        self,
        limit_type: str,
        limit: int,
        window_seconds: int,
        retry_after: int,
    ):
        self.limit_type = limit_type
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded: {limit_type}")


class RateLimiter:
    """
    Ограничитель скорости на основе Redis с алгоритмом скользящего окна.
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        identifier: str = "request",
        is_calendar_limit: bool = False,
    ) -> dict[str, int]:
        """
        Проверяет ограничение скорости.

        Args:
            key: Redis ключ для этого ограничения скорости
            limit: Максимальное количество разрешенных запросов
            window_seconds: Временное окно в секундах
            identifier: Читаемый идентификатор для логирования
            is_calendar_limit: Календарный лимит (сброс в 00:00 MSK) или скользящее окно

        Returns:
            Словарь с оставшимися запросами и временем сброса

        Raises:
            RateLimitExceeded: Когда ограничение скорости превышено
        """
        try:
            if is_calendar_limit:
                return await self._check_calendar_limit(key, limit, identifier)
            else:
                return await self._check_sliding_window_limit(
                    key, limit, window_seconds, identifier
                )

        except RateLimitExceeded:
            raise
        except Exception as e:
            log.error(
                "rate_limit.redis.error",
                key=key,
                identifier=identifier,
                error=str(e),
            )
            # Мягкая деградация - разрешаем запрос, если Redis недоступен
            if is_calendar_limit:
                moscow_tz = timezone(timedelta(hours=3))
                now_moscow = datetime.now(moscow_tz)
                tomorrow = (now_moscow + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                reset_time = int(tomorrow.timestamp())
            else:
                reset_time = int(time.time()) + window_seconds

            return {
                "remaining": limit - 1,
                "reset_time": reset_time,
                "current": 1,
            }

    async def _check_calendar_limit(
        self, key: str, limit: int, identifier: str
    ) -> dict[str, int]:
        """
        Проверяет календарный лимит (сброс в 00:00 по Москве).
        """
        # Получаем текущий счетчик
        current_count = await self.redis.zcard(key)

        if current_count >= limit:
            log.warning(
                "rate_limit.calendar.exceeded",
                key=key,
                identifier=identifier,
                current_count=current_count,
                limit=limit,
            )

            # Вычисляем время сброса (00:00 следующего дня MSK)
            moscow_tz = timezone(timedelta(hours=3))
            now_moscow = datetime.now(moscow_tz)
            tomorrow = (now_moscow + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            seconds_until_reset = int((tomorrow - now_moscow).total_seconds())

            raise RateLimitExceeded(
                limit_type=identifier,
                limit=limit,
                window_seconds=86400,  # 24 hours for display
                retry_after=seconds_until_reset,
            )

        # Добавляем запись о текущем использовании
        current_time = int(time.time())
        await self.redis.zadd(
            key, {f"{current_time}:{uuid.uuid4()}": current_time}
        )

        # Устанавливаем TTL до конца дня + 1 час
        moscow_tz = timezone(timedelta(hours=3))
        now_moscow = datetime.now(moscow_tz)
        tomorrow = (now_moscow + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        ttl_seconds = (
            int((tomorrow - now_moscow).total_seconds()) + 3600
        )  # +1 hour buffer
        await self.redis.expire(key, ttl_seconds)

        remaining = max(0, limit - current_count - 1)
        reset_time = int(tomorrow.timestamp())

        log.debug(
            "rate_limit.calendar.passed",
            key=key,
            identifier=identifier,
            current_count=current_count + 1,
            limit=limit,
            remaining=remaining,
        )

        return {
            "remaining": remaining,
            "reset_time": reset_time,
            "current": current_count + 1,
        }

    async def _check_sliding_window_limit(
        self, key: str, limit: int, window_seconds: int, identifier: str
    ) -> dict[str, int]:
        """
        Проверяет лимит с алгоритмом скользящего окна.
        """
        current_time = int(time.time())
        window_start = current_time - window_seconds

        # Используем Redis pipeline для атомарных операций
        pipe = self.redis.pipeline()

        # Удаляем просроченные записи
        pipe.zremrangebyscore(key, 0, window_start)

        # Подсчитываем текущие запросы в окне
        pipe.zcard(key)

        # Добавляем текущий запрос
        pipe.zadd(key, {f"{current_time}:{uuid.uuid4()}": current_time})

        # Устанавливаем TTL для очистки
        pipe.expire(key, window_seconds + 1)

        results = await pipe.execute()
        current_count = results[
            1
        ]  # Количество после удаления просроченных записей

        remaining = max(0, limit - current_count - 1)
        reset_time = current_time + window_seconds

        if current_count >= limit:
            log.warning(
                "rate_limit.exceeded",
                key=key,
                identifier=identifier,
                current_count=current_count,
                limit=limit,
                window_seconds=window_seconds,
            )

            raise RateLimitExceeded(
                limit_type=identifier,
                limit=limit,
                window_seconds=window_seconds,
                retry_after=window_seconds,
            )

        log.debug(
            "rate_limit.passed",
            key=key,
            identifier=identifier,
            current_count=current_count + 1,
            limit=limit,
            remaining=remaining,
        )

        return {
            "remaining": remaining,
            "reset_time": reset_time,
            "current": current_count + 1,
        }

    async def check_ip_rate_limit(
        self, ip: str, endpoint_type: str = "general"
    ) -> dict[str, int]:
        """
        Проверяет ограничения скорости на основе IP-адреса.

        Args:
            ip: IP-адрес клиента
            endpoint_type: Тип эндпоинта ('auth' или 'general')
        """
        if endpoint_type == "auth":
            limit = settings.RATE_LIMIT_IP_AUTH_PER_SECOND
            window = 1
            key = f"rate_limit:ip:{ip}:auth:second"
        else:
            limit = settings.RATE_LIMIT_IP_GENERAL_PER_SECOND
            window = 1
            key = f"rate_limit:ip:{ip}:general:second"

        return await self.check_rate_limit(
            key=key,
            limit=limit,
            window_seconds=window,
            identifier=f"IP-{endpoint_type}",
        )

    async def check_user_rate_limit(
        self,
        user_id: uuid.UUID,
        operation_type: str = "general",
        subscription_tier: str = "free",
    ) -> dict[str, int]:
        """
        Проверяет ограничения скорости на основе пользователя.

        Args:
            user_id: UUID пользователя
            operation_type: Тип операции ('general', 'write' и т.д.)
            subscription_tier: Тарифный план пользователя
        """
        tier_limits = settings.SUBSCRIPTION_LIMITS.get(
            subscription_tier, settings.SUBSCRIPTION_LIMITS["free"]
        )

        if operation_type == "write":
            limit = tier_limits["user_write_per_hour"]
            window = 3600
            key = f"rate_limit:user:{user_id}:write:hour"
        else:
            limit = tier_limits["user_general_per_hour"]
            window = 3600
            key = f"rate_limit:user:{user_id}:general:hour"

        return await self.check_rate_limit(
            key=key,
            limit=limit,
            window_seconds=window,
            identifier=f"User-{operation_type}",
        )

    async def check_resource_limit(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        time_window: str = "daily",
        subscription_tier: str = "free",
    ) -> dict[str, int]:
        """
        Проверяет ограничения на конкретные ресурсы (стратегии, бэктесты и т.д.).

        Args:
            user_id: UUID пользователя
            resource_type: Тип ресурса ('strategies', 'backtests')
            time_window: Временное окно ('daily', 'concurrent')
            subscription_tier: Тарифный план пользователя
        """
        tier_limits = settings.SUBSCRIPTION_LIMITS.get(
            subscription_tier, settings.SUBSCRIPTION_LIMITS["free"]
        )

        if resource_type == "strategies" and time_window == "daily":
            limit = tier_limits["strategies_per_day"]
            window = 86400  # 24 hours
            # Добавляем дату по MSK для календарного сброса
            moscow_tz = timezone(timedelta(hours=3))
            today_moscow = datetime.now(moscow_tz).strftime("%Y-%m-%d")
            key = f"rate_limit:user:{user_id}:strategies:daily:{today_moscow}"
        elif resource_type == "backtests" and time_window == "daily":
            limit = tier_limits["backtests_per_day"]
            window = 86400
            # Добавляем дату по MSK для календарного сброса
            moscow_tz = timezone(timedelta(hours=3))
            today_moscow = datetime.now(moscow_tz).strftime("%Y-%m-%d")
            key = f"rate_limit:user:{user_id}:backtests:daily:{today_moscow}"
        elif resource_type == "backtests" and time_window == "concurrent":
            # Для одновременных бэктестов используем более простой счетчик
            limit = tier_limits["concurrent_backtests"]
            window = 3600  # Проверяем почасово, но представляет количество одновременных
            key = f"rate_limit:user:{user_id}:backtests:concurrent"
        else:
            raise ValueError(
                f"Unknown resource limit: {resource_type}:{time_window}"
            )

        # Календарные лимиты (сброс в 00:00 MSK) для daily, sliding window для concurrent
        is_calendar = time_window == "daily"

        return await self.check_rate_limit(
            key=key,
            limit=limit,
            window_seconds=window,
            identifier=f"Resource-{resource_type}-{time_window}",
            is_calendar_limit=is_calendar,
        )


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для применения ограничений скорости к входящим запросам.
    """

    def __init__(self, app, redis_getter=None, redis: Redis = None):
        super().__init__(app)
        self.redis_getter = redis_getter
        self.redis = redis
        self.rate_limiter = None

    def _get_client_ip(self, request: Request) -> str:
        """Получает IP-адрес клиента, обрабатывая прокси."""
        # Сначала проверяем заголовок X-Forwarded-For (для балансировщиков/прокси)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Берем первый IP в цепочке
            return forwarded_for.split(",")[0].strip()

        # Проверяем заголовок X-Real-IP (nginx proxy)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Возвращаемся к IP прямого соединения
        return request.client.host if request.client else "unknown"

    def _is_auth_endpoint(self, path: str) -> bool:
        """Проверяет, относится ли эндпоинт к аутентификации."""
        return path.startswith("/api/v1/auth/")

    def _is_health_endpoint(self, path: str) -> bool:
        """Проверяет, является ли эндпоинт проверкой здоровья (исключены из ограничений)."""
        return path in ["/", "/api/v1/docs", "/api/v1/openapi.json"]

    async def dispatch(self, request: Request, call_next):
        """Применяет ограничение скорости к запросам."""
        path = request.url.path

        # Пропускаем ограничение скорости для проверок здоровья
        if self._is_health_endpoint(path):
            return await call_next(request)

        # Инициализируем rate_limiter если еще не инициализирован
        if self.rate_limiter is None:
            if self.redis_getter:
                redis = self.redis_getter()
            elif self.redis:
                redis = self.redis
            else:
                # Если Redis недоступен, пропускаем запрос
                return await call_next(request)

            self.rate_limiter = RateLimiter(redis)

        client_ip = self._get_client_ip(request)

        try:
            # Применяем ограничение на основе IP
            endpoint_type = (
                "auth" if self._is_auth_endpoint(path) else "general"
            )
            ip_limit_info = await self.rate_limiter.check_ip_rate_limit(
                client_ip, endpoint_type
            )

            # Обрабатываем запрос
            response = await call_next(request)

            # Добавляем заголовки ограничения скорости к успешным ответам
            response.headers["X-RateLimit-Limit-IP"] = str(
                settings.RATE_LIMIT_IP_AUTH_PER_SECOND
                if endpoint_type == "auth"
                else settings.RATE_LIMIT_IP_GENERAL_PER_SECOND
            )
            response.headers["X-RateLimit-Remaining-IP"] = str(
                ip_limit_info["remaining"]
            )
            response.headers["X-RateLimit-Reset-IP"] = str(
                ip_limit_info["reset_time"]
            )

            return response

        except RateLimitExceeded as e:
            log.warning(
                "rate_limit.exceeded.middleware",
                client_ip=client_ip,
                path=path,
                limit_type=e.limit_type,
                limit=e.limit,
                window_seconds=e.window_seconds,
            )

            # Возвращаем 429 Too Many Requests
            error_response = ErrorResponse(
                type="https://trade-forge.ru/errors/rate-limit-exceeded",
                title="Rate Limit Exceeded",
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {e.limit_type}. "
                f"Limit: {e.limit} requests per {e.window_seconds} second(s).",
                instance=str(request.url),
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=error_response.model_dump(exclude_none=True),
                headers={
                    "Retry-After": str(e.retry_after),
                    "X-RateLimit-Limit": str(e.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(
                        int(time.time()) + e.window_seconds
                    ),
                },
            )

        except Exception as e:
            log.error(
                "rate_limit.middleware.error",
                client_ip=client_ip,
                path=path,
                error=str(e),
                exc_info=True,
            )
            # Продолжаем с запросом при неожиданных ошибках
            return await call_next(request)


# Совместимость с существующим кодом
async def check_user_rate_limits(
    redis: Redis,
    user_id: uuid.UUID,
    method: str,
    subscription_tier: str = "free",
    resource_type: Optional[str] = None,
) -> None:
    """
    Вспомогательная функция для проверки пользовательских ограничений скорости в эндпоинтах.

    Args:
        redis: Redis клиент
        user_id: UUID пользователя
        method: HTTP метод
        subscription_tier: Тарифный план пользователя
        resource_type: Тип ресурса, к которому осуществляется доступ (для ограничений по ресурсам)

    Raises:
        HTTPException: Когда превышен лимит скорости
    """
    rate_limiter = RateLimiter(redis)

    try:
        # Проверяем общий лимит пользователя
        await rate_limiter.check_user_rate_limit(
            user_id, "general", subscription_tier
        )

        # Проверяем лимиты операций записи для модифицирующих операций
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            await rate_limiter.check_user_rate_limit(
                user_id, "write", subscription_tier
            )

        # Проверяем ограничения для конкретных ресурсов
        if resource_type == "strategy" and method == "POST":
            await rate_limiter.check_resource_limit(
                user_id, "strategies", "daily", subscription_tier
            )
        elif resource_type == "backtest" and method == "POST":
            await rate_limiter.check_resource_limit(
                user_id, "backtests", "daily", subscription_tier
            )

    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for {e.limit_type}. "
            f"Limit: {e.limit} requests per {e.window_seconds} seconds.",
            headers={
                "Retry-After": str(e.retry_after),
                "X-RateLimit-Limit": str(e.limit),
                "X-RateLimit-Remaining": "0",
            },
        )
