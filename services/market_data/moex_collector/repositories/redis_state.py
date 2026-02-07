"""
Redis State Manager для отслеживания состояния сборов.

Хранит последние даты собранных свечей с fallback на ClickHouse.
"""

from __future__ import annotations

from datetime import datetime

from redis.asyncio import Redis
from tradeforge_logger import get_logger

from repositories.clickhouse import ClickHouseRepository

logger = get_logger(__name__)

# Формат дат в Redis
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class RedisStateManager:
    """
    Менеджер состояния сборов в Redis.

    Хранит последние даты собранных данных для отслеживания прогресса.
    При недоступности Redis использует fallback на ClickHouse.
    """

    def __init__(
        self,
        redis_client: Redis,
        clickhouse_repo: ClickHouseRepository,
    ):
        """
        Инициализация state manager.

        Args:
            redis_client: Асинхронный Redis клиент
            clickhouse_repo: ClickHouse репозиторий для fallback
        """
        self.redis = redis_client
        self.clickhouse_repo = clickhouse_repo

    def _make_key(self, ticker: str, timeframe: str) -> str:
        """
        Формирует Redis ключ для тикера и таймфрейма.

        Args:
            ticker: Алиас тикера
            timeframe: Таймфрейм

        Returns:
            Redis ключ
        """
        return f"candles_collector:{ticker}_{timeframe}"

    async def get_last_candle_date(
        self, ticker: str, timeframe: str
    ) -> datetime | None:
        """
        Получает дату последней собранной свечи.

        При недоступности Redis использует fallback на ClickHouse.

        Args:
            ticker: Алиас тикера
            timeframe: Таймфрейм

        Returns:
            Datetime последней свечи или None
        """
        redis_key = self._make_key(ticker, timeframe)

        try:
            # Пытаемся получить из Redis
            value = await self.redis.get(redis_key)

            if value:
                # Redis возвращает bytes или str в зависимости от decode_responses
                value_str = (
                    value.decode("utf-8")
                    if isinstance(value, bytes)
                    else value
                )
                date = datetime.strptime(value_str, TIME_FORMAT)
                logger.debug(
                    "redis_state.date_from_redis",
                    ticker=ticker,
                    timeframe=timeframe,
                    date=value_str,
                )
                return date

            logger.debug(
                "redis_state.no_date_in_redis",
                ticker=ticker,
                timeframe=timeframe,
            )
            return None

        except Exception as e:
            # Redis недоступен - fallback на ClickHouse
            logger.warning(
                "redis_state.unavailable_using_clickhouse",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
            )

            try:
                return await self.clickhouse_repo.get_latest_candle_date(
                    ticker, timeframe
                )
            except Exception as ch_error:
                logger.error(
                    "redis_state.clickhouse_fallback_failed",
                    ticker=ticker,
                    timeframe=timeframe,
                    error=str(ch_error),
                    exc_info=True,
                )
                return None

    async def update_last_candle_date(
        self, ticker: str, timeframe: str, date: datetime
    ) -> None:
        """
        Обновляет дату последней собранной свечи в Redis.

        Args:
            ticker: Алиас тикера
            timeframe: Таймфрейм
            date: Datetime последней свечи
        """
        redis_key = self._make_key(ticker, timeframe)
        date_str = date.strftime(TIME_FORMAT)

        try:
            await self.redis.set(redis_key, date_str)

            logger.debug(
                "redis_state.date_updated",
                ticker=ticker,
                timeframe=timeframe,
                date=date_str,
            )

        except Exception as e:
            # Не критично если не удалось обновить Redis
            # Данные в ClickHouse уже сохранены
            logger.warning(
                "redis_state.update_failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
            )

    async def sync_with_clickhouse(self) -> int:
        """
        Синхронизирует состояние Redis с ClickHouse.

        Обновляет все ключи в Redis на основе реальных данных из ClickHouse.
        Полезно при старте сервиса или после downtime Redis.

        Returns:
            Количество обновленных ключей
        """
        logger.info("redis_state.sync_starting")

        try:
            # Получаем все последние даты из ClickHouse
            ch_latest_dates = await self.clickhouse_repo.get_latest_dates()

            if not ch_latest_dates:
                logger.warning("redis_state.no_clickhouse_data")
                return 0

            # Формируем Redis ключи
            redis_keys_map = {
                f"candles_collector:{key}": key
                for key in ch_latest_dates.keys()
            }
            redis_keys = list(redis_keys_map.keys())

            # Получаем текущие значения из Redis
            redis_values = await self.redis.mget(redis_keys)

            # Определяем какие ключи нужно обновить
            updates_to_make: dict[str, str] = {}

            for i, redis_key in enumerate(redis_keys):
                redis_value = redis_values[i]

                # Обрабатываем bytes/str/None
                if redis_value is None:
                    redis_date_str = None
                elif isinstance(redis_value, bytes):
                    redis_date_str = redis_value.decode("utf-8")
                else:
                    redis_date_str = redis_value

                original_key = redis_keys_map[redis_key]
                ch_date = ch_latest_dates[original_key]
                ch_date_str = ch_date.strftime(TIME_FORMAT)

                # Обновляем если даты различаются
                if redis_date_str != ch_date_str:
                    updates_to_make[redis_key] = ch_date_str
                    logger.debug(
                        "redis_state.sync_update",
                        key=redis_key,
                        redis_date=redis_date_str,
                        clickhouse_date=ch_date_str,
                    )

            # Массово обновляем ключи
            if updates_to_make:
                await self.redis.mset(updates_to_make)
                logger.info(
                    "redis_state.sync_completed",
                    updated=len(updates_to_make),
                )
            else:
                logger.info("redis_state.sync_no_updates_needed")

            return len(updates_to_make)

        except Exception as e:
            logger.error(
                "redis_state.sync_failed",
                error=str(e),
                exc_info=True,
            )
            return 0
