"""
Сервис для работы с лимитами пользователей.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis

from app.core.rate_limiting import RateLimiter
from app.schemas.limits import LimitInfo, UserLimitsResponse
from app.settings import settings


class LimitsService:
    """Сервис для получения информации о лимитах пользователя."""

    def __init__(self, redis: Redis):
        self.redis = redis
        self.rate_limiter = RateLimiter(redis)

    def _get_moscow_reset_time(self) -> datetime:
        """Получает время сброса лимитов (00:00 следующего дня по МСК)."""
        moscow_tz = timezone(timedelta(hours=3))
        now_moscow = datetime.now(moscow_tz)
        tomorrow = (now_moscow + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Возвращаем время в московском часовом поясе, а не в UTC
        return tomorrow

    async def _get_current_usage(
        self, user_id: uuid.UUID, limit_type: str
    ) -> int:
        """
        Получает текущее использование лимита из Redis.

        Args:
            user_id: ID пользователя
            limit_type: Тип лимита ('strategies', 'backtests', 'concurrent')

        Returns:
            Количество использованных единиц
        """
        try:
            # Для календарных лимитов используем ключи с датой
            if limit_type in ("strategies", "backtests"):
                moscow_tz = timezone(timedelta(hours=3))
                today_moscow = datetime.now(moscow_tz).strftime("%Y-%m-%d")
                key = f"rate_limit:user:{user_id}:{limit_type}:daily:{today_moscow}"
            else:
                # Для concurrent лимитов используем обычные ключи
                key = f"rate_limit:user:{user_id}:{limit_type}:concurrent"

            # Получаем количество записей в sorted set
            count = await self.redis.zcard(key)
            return count if count else 0

        except Exception:
            # В случае ошибки Redis возвращаем 0
            return 0

    async def get_user_limits(
        self, user_id: uuid.UUID, subscription_tier: str
    ) -> UserLimitsResponse:
        """
        Получает полную информацию о лимитах пользователя.

        Args:
            user_id: ID пользователя
            subscription_tier: Тарифный план пользователя

        Returns:
            Объект с лимитами пользователя
        """
        # Получаем лимиты для тарифа
        tier_limits = settings.SUBSCRIPTION_LIMITS.get(
            subscription_tier, settings.SUBSCRIPTION_LIMITS["free"]
        )

        reset_time = self._get_moscow_reset_time()

        # Получаем текущее использование
        strategies_used = await self._get_current_usage(user_id, "strategies")
        backtests_used = await self._get_current_usage(user_id, "backtests")
        concurrent_used = await self._get_current_usage(user_id, "concurrent")

        return UserLimitsResponse(
            subscription_tier=subscription_tier,
            strategies_per_day=LimitInfo(
                limit=tier_limits["strategies_per_day"],
                used=strategies_used,
                remaining=max(
                    0, tier_limits["strategies_per_day"] - strategies_used
                ),
                reset_time=reset_time,
            ),
            backtests_per_day=LimitInfo(
                limit=tier_limits["backtests_per_day"],
                used=backtests_used,
                remaining=max(
                    0, tier_limits["backtests_per_day"] - backtests_used
                ),
                reset_time=reset_time,
            ),
            concurrent_backtests=LimitInfo(
                limit=tier_limits["concurrent_backtests"],
                used=concurrent_used,
                remaining=max(
                    0, tier_limits["concurrent_backtests"] - concurrent_used
                ),
                reset_time=reset_time,
            ),
            backtest_max_years=LimitInfo(
                limit=tier_limits["backtest_max_years"],
                used=0,  # Это не счетчик, а ограничение
                remaining=tier_limits["backtest_max_years"],
                reset_time=reset_time,
            ),
        )

    async def check_can_create_strategy(
        self, user_id: uuid.UUID, subscription_tier: str
    ) -> bool:
        """Проверяет, может ли пользователь создать стратегию."""
        limits = await self.get_user_limits(user_id, subscription_tier)
        return limits.strategies_per_day.remaining > 0

    async def check_can_create_backtest(
        self, user_id: uuid.UUID, subscription_tier: str
    ) -> bool:
        """Проверяет, может ли пользователь запустить бэктест."""
        limits = await self.get_user_limits(user_id, subscription_tier)
        return (
            limits.backtests_per_day.remaining > 0
            and limits.concurrent_backtests.remaining > 0
        )
