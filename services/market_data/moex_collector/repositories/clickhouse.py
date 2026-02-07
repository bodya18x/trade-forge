"""
Репозиторий для работы с ClickHouse.

Асинхронные операции с хранилищем свечей и индикаторов.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pyarrow as pa
from tradeforge_logger import get_logger

from managers import ClickHouseClientPool
from models import MOSCOW_TZ

logger = get_logger(__name__)


class ClickHouseRepository:
    """
    Репозиторий для работы с ClickHouse.

    Предоставляет методы для сохранения свечей и получения
    последних дат сбора.

    Использует пул асинхронных клиентов для эффективной работы.
    """

    def __init__(self, pool: ClickHouseClientPool):
        """
        Инициализация репозитория.

        Args:
            pool: Пул асинхронных клиентов ClickHouse
        """
        self.pool = pool

    async def save_candles_batch(self, candles: list[dict[str, Any]]) -> None:
        """
        Пакетная вставка свечей в trader.candles_base.

        Args:
            candles: Список словарей с данными свечей

        Raises:
            Exception: При ошибке вставки
        """
        if not candles:
            logger.debug("clickhouse.no_candles_to_save")
            return

        client = await self.pool.acquire()

        try:
            # Преобразуем datetime для ClickHouse
            processed_candles = []
            for candle in candles:
                c = candle.copy()

                # Обработка datetime
                if isinstance(c["begin"], str):
                    dt = datetime.fromisoformat(c["begin"])
                else:
                    dt = c["begin"]

                # Убеждаемся что datetime имеет московскую таймзону
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=MOSCOW_TZ)
                else:
                    dt = dt.astimezone(MOSCOW_TZ)

                c["begin"] = dt
                processed_candles.append(c)

            # Используем PyArrow для быстрой вставки
            table = pa.Table.from_pylist(processed_candles)
            await client.insert_arrow("trader.candles_base", table)

            logger.info(
                "clickhouse.candles_saved",
                count=len(candles),
                ticker=candles[0].get("ticker"),
                timeframe=candles[0].get("timeframe"),
            )

        except Exception as exc:
            logger.error(
                "clickhouse.save_candles_failed",
                count=len(candles),
                error=str(exc),
                exc_info=True,
            )
            raise
        finally:
            await self.pool.release(client)

    async def get_latest_candle_date(
        self, ticker: str, timeframe: str
    ) -> datetime | None:
        """
        Получает дату последней свечи для тикера и таймфрейма.

        Args:
            ticker: Алиас тикера
            timeframe: Таймфрейм

        Returns:
            Datetime последней свечи или None

        Raises:
            Exception: При ошибке запроса
        """
        client = await self.pool.acquire()

        try:
            query = """
                SELECT max(begin) AS last_begin
                FROM trader.candles_base
                WHERE ticker = {ticker:String}
                  AND timeframe = {timeframe:String}
            """

            result = await client.query(
                query,
                parameters={"ticker": ticker, "timeframe": timeframe},
            )

            if not result.result_rows:
                return None

            last_begin = result.result_rows[0][0]

            if not last_begin:
                return None

            # Добавляем таймзону если нужно
            if last_begin.tzinfo is None:
                last_begin = last_begin.replace(tzinfo=MOSCOW_TZ)
            else:
                last_begin = last_begin.astimezone(MOSCOW_TZ)

            logger.debug(
                "clickhouse.latest_candle_date",
                ticker=ticker,
                timeframe=timeframe,
                date=last_begin.isoformat(),
            )

            return last_begin

        except Exception as e:
            logger.error(
                "clickhouse.get_latest_date_failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
                exc_info=True,
            )
            raise
        finally:
            await self.pool.release(client)

    async def get_latest_dates(self) -> dict[str, datetime]:
        """
        Получает последние даты свечей для всех пар (ticker, timeframe).

        Returns:
            Словарь {ticker_timeframe: datetime}

        Raises:
            Exception: При ошибке запроса
        """
        client = await self.pool.acquire()

        try:
            query = """
                SELECT
                    ticker,
                    timeframe,
                    max(begin) AS last_begin
                FROM trader.candles_base
                GROUP BY ticker, timeframe
            """

            result = await client.query(query)
            latest_dates = {}

            for row in result.result_rows:
                ticker, tf, last_begin_dt = row

                if not last_begin_dt:
                    continue

                # Добавляем таймзону
                if last_begin_dt.tzinfo is None:
                    last_begin_dt = last_begin_dt.replace(tzinfo=MOSCOW_TZ)
                else:
                    last_begin_dt = last_begin_dt.astimezone(MOSCOW_TZ)

                key = f"{ticker}_{tf}"
                latest_dates[key] = last_begin_dt

            logger.info(
                "clickhouse.latest_dates_loaded",
                count=len(latest_dates),
            )

            return latest_dates

        except Exception as e:
            logger.error(
                "clickhouse.get_latest_dates_failed",
                error=str(e),
                exc_info=True,
            )
            return {}
        finally:
            await self.pool.release(client)
