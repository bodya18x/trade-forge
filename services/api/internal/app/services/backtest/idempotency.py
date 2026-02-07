"""
Управление идемпотентностью бэктестов.

Использует Redis для хранения и проверки ключей идемпотентности.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from redis.asyncio import Redis
from tradeforge_logger import get_logger

from app.types import BacktestJobID, UserID

log = get_logger(__name__)


class IdempotencyManager:
    """
    Менеджер идемпотентности для бэктестов.

    Обеспечивает защиту от повторной обработки одинаковых запросов
    используя Redis для хранения ключей.
    """

    def __init__(self, redis: Redis, user_id: UserID):
        """
        Инициализирует менеджер идемпотентности.

        Args:
            redis: Клиент Redis
            user_id: UUID пользователя
        """
        self.redis = redis
        self.user_id = user_id

    async def check_idempotency(
        self, idempotency_key: str | None, request_hash: str
    ) -> str | None:
        """
        Проверяет идемпотентность запроса.

        Args:
            idempotency_key: Ключ идемпотентности
            request_hash: Хэш запроса для проверки совпадения

        Returns:
            job_id если запрос уже был обработан, None если запрос новый

        Raises:
            HTTPException: Если ключ используется с другим payload
        """
        if not idempotency_key:
            return None

        redis_key = f"idempotency:backtest:{self.user_id}:{idempotency_key}"
        cached_value = await self.redis.get(redis_key)

        if cached_value:
            cached_hash, job_id = cached_value.split(":", 1)
            if cached_hash == request_hash:
                log.info("idempotency.hit", key=idempotency_key, job_id=job_id)
                return job_id
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key is being used with a different request payload.",
                )

        return None

    async def store_idempotency_key(
        self, idempotency_key: str, request_hash: str, job_id: BacktestJobID
    ) -> None:
        """
        Сохраняет ключ идемпотентности в Redis.

        Args:
            idempotency_key: Ключ идемпотентности
            request_hash: Хэш запроса
            job_id: UUID созданной задачи
        """
        if not idempotency_key:
            return

        redis_key = f"idempotency:backtest:{self.user_id}:{idempotency_key}"
        value = f"{request_hash}:{job_id}"
        # Ключ живет 24 часа
        await self.redis.set(redis_key, value, ex=86400)
