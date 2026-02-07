"""
Модуль для работы с Redis кэшем.

Управляет пулом соединений Redis для кэширования данных.
"""

from __future__ import annotations

from redis.asyncio import Redis, from_url
from tradeforge_logger import get_logger

from app.settings import settings

log = get_logger(__name__)

# Создаем глобальный клиент Redis, который будет инициализирован при старте
redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """
    Возвращает экземпляр клиента Redis.

    Гарантирует, что клиент инициализирован.

    Returns:
        Redis клиент для использования в endpoints

    Raises:
        RuntimeError: Если Redis клиент не инициализирован
    """
    if redis_client is None:
        log.error("redis.client.not_initialized")
        raise RuntimeError("Redis client has not been initialized.")
    return redis_client


async def init_redis_pool():
    """
    Инициализирует пул соединений Redis при старте приложения.

    Raises:
        Exception: Если не удалось установить соединение с Redis
    """
    global redis_client

    log.info("redis.pool.initializing", dsn=settings.REDIS_DSN)

    try:
        redis_client = await from_url(
            settings.REDIS_DSN, encoding="utf-8", decode_responses=True
        )

        # Проверяем соединение
        await redis_client.ping()
        log.info("redis.connection.established")

    except Exception as e:
        log.error(
            "failed_to_initialize_redis",
            error=str(e),
            dsn=settings.REDIS_DSN,
            exc_info=True,
        )
        raise


async def close_redis_pool():
    """Закрывает пул соединений Redis при остановке приложения."""
    global redis_client

    if redis_client:
        log.info("redis.pool.closing")
        try:
            await redis_client.close()
            log.info("redis.connection.closed")
        except Exception as e:
            log.error(
                "error_closing_redis_connection",
                error=str(e),
                exc_info=True,
            )
        finally:
            redis_client = None
