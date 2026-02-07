"""
Управление соединениями Redis для ограничения скорости и кэширования.
"""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis
from tradeforge_logger import get_logger

from app.settings import settings

log = get_logger(__name__)

# Глобальный пул соединений Redis (объединенный)
_redis_pool = None


def init_redis_pools():
    """Инициализирует пул соединений Redis (объединенный для всех целей)."""
    global _redis_pool

    try:
        # Объединенный пул Redis (для всех целей: сессии, ограничение скорости и т.д.)
        _redis_pool = ConnectionPool.from_url(
            settings.REDIS_DSN,
            encoding="utf-8",
            decode_responses=True,
            max_connections=30,  # Увеличено, так как используем один пул для всего
        )

        log.info(
            "redis.pool.initialized",
            redis_db=settings.REDIS_DB,
        )

    except Exception as e:
        log.error(
            "redis.pool.initialization.failed",
            error=str(e),
            exc_info=True,
        )
        raise


async def close_redis_pools():
    """Закрывает пул соединений Redis."""
    global _redis_pool

    try:
        if _redis_pool:
            await _redis_pool.aclose()
            _redis_pool = None

        log.info("redis.pool.closed")

    except Exception as e:
        log.error(
            "redis.pool.close.error",
            error=str(e),
            exc_info=True,
        )


def get_main_redis() -> Redis:
    """Получает основной клиент Redis."""
    if _redis_pool is None:
        raise RuntimeError(
            "Redis pool not initialized. Call init_redis_pools() first."
        )

    return Redis(connection_pool=_redis_pool)


def get_rate_limit_redis() -> Redis:
    """Получает Redis клиент для ограничения скорости (тот же что и основной)."""
    if _redis_pool is None:
        raise RuntimeError(
            "Redis pool not initialized. Call init_redis_pools() first."
        )

    return Redis(connection_pool=_redis_pool)


async def health_check_redis() -> dict[str, bool]:
    """
    Выполняет проверку здоровья объединенного экземпляра Redis.

    Returns:
        Словарь со статусом здоровья основного Redis и Redis ограничения скорости (тот же экземпляр)
    """
    redis_healthy = False

    try:
        # Проверяем объединенный Redis
        redis_client = get_main_redis()
        await redis_client.ping()
        redis_healthy = True
        await redis_client.aclose()

    except Exception as e:
        log.error("redis.health.check.failed", error=str(e))

    # Возвращаем одинаковый статус для обеих ключей для обратной совместимости
    return {"main_redis": redis_healthy, "rate_limit_redis": redis_healthy}
