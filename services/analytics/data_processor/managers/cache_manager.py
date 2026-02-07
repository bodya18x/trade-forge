"""
Cache Manager для работы с Redis.

Управляет кэшем контекста свечей для расчета индикаторов.
"""

import json
from typing import Any

from redis import asyncio as aioredis
from tradeforge_logger import get_logger

from core.constants import (
    DEFAULT_CONTEXT_CANDLES_SIZE,
    REDIS_CONTEXT_KEY_PREFIX,
)
from settings import settings

logger = get_logger(__name__)


class CacheManager:
    """
    Менеджер кэша для контекста свечей в Redis.

    Использует Redis Lists для эффективного хранения последних N свечей,
    необходимых для расчета индикаторов с lookback периодом.

    Attributes:
        redis_client: Асинхронный Redis клиент.
        max_items: Максимальное количество свечей в контексте.
    """

    def __init__(self, max_items: int = DEFAULT_CONTEXT_CANDLES_SIZE):
        """
        Инициализирует асинхронный Redis клиент.

        Args:
            max_items: Максимальное количество свечей в контексте.
        """
        self.redis_client = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
        )
        self.max_items = max_items
        logger.info("cache_manager.initialized", max_items=max_items)

    async def close(self) -> None:
        """Закрывает Redis соединение при graceful shutdown."""
        try:
            await self.redis_client.aclose()
            logger.info("cache_manager.closed")
        except Exception as e:
            logger.warning("cache_manager.close_error", error=str(e))

    async def get_context_candles(
        self, ticker: str, timeframe: str
    ) -> list[dict[str, Any]]:
        """
        Получает последние N свечей из Redis для контекста.

        Args:
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.

        Returns:
            Список свечей в формате dict.
        """
        redis_key = self._make_redis_key(ticker, timeframe)

        try:
            raw_candles = await self.redis_client.lrange(
                redis_key, -self.max_items, -1
            )

            candles = []
            for raw in raw_candles:
                try:
                    candles.append(json.loads(raw))
                except json.JSONDecodeError:
                    logger.warning(
                        "cache_manager.json_decode_error",
                        ticker=ticker,
                        timeframe=timeframe,
                        raw_preview=raw[:100],
                    )
                    continue

            logger.debug(
                "cache_manager.context_loaded",
                ticker=ticker,
                timeframe=timeframe,
                candles_count=len(candles),
            )

            return candles

        except aioredis.RedisError as e:
            logger.error(
                "cache_manager.redis_error",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
            )
            return []

    async def update_context_cache(
        self, ticker: str, timeframe: str, new_candle: dict[str, Any]
    ) -> None:
        """
        Добавляет новую свечу в конец списка и обрезает до max_items.

        Args:
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            new_candle: Новая свеча для добавления.
        """
        redis_key = self._make_redis_key(ticker, timeframe)

        try:
            pipeline = self.redis_client.pipeline()
            pipeline.rpush(redis_key, json.dumps(new_candle))
            pipeline.ltrim(redis_key, -self.max_items, -1)
            await pipeline.execute()

            logger.debug(
                "cache_manager.context_updated",
                ticker=ticker,
                timeframe=timeframe,
            )

        except aioredis.RedisError as e:
            logger.warning(
                "cache_manager.update_error",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
            )

    @staticmethod
    def _make_redis_key(ticker: str, timeframe: str) -> str:
        """
        Формирует ключ для Redis.

        Args:
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.

        Returns:
            Ключ вида "candles_context:TICKER:TIMEFRAME".
        """
        return f"{REDIS_CONTEXT_KEY_PREFIX}:{ticker}:{timeframe}"
