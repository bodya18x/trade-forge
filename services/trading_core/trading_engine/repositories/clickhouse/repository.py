"""
ClickHouse Repository для Trading Engine.

Асинхронный репозиторий для загрузки данных для бэктестов:
- Базовые свечи (OHLCV)
- Значения индикаторов
- Проверка полноты данных
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Union

from clickhouse_connect.driver.asyncclient import AsyncClient
from clickhouse_connect.driver.exceptions import ClickHouseError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tradeforge_logger import get_logger

from core.common import (
    CLICKHOUSE_DUMMY_INDICATOR_PAIR,
    SLOW_QUERY_THRESHOLD_MS,
)

logger = get_logger(__name__)

# Оптимизированный UNION ALL запрос с PREWHERE для высокой производительности
# PREWHERE фильтрует по ticker/timeframe ДО чтения остальных колонок
# WHERE применяется к date range ПОСЛЕ чтения базовых колонок
GET_BACKTEST_DATA_QUERY = """
SELECT 'candle' as data_type, ticker, timeframe, begin, open, high, low, close, volume, '' as indicator_key, '' as value_key, 0.0 as value
FROM trader.candles_base
PREWHERE ticker = %(ticker)s AND timeframe = %(timeframe)s
WHERE begin >= %(start_date)s AND begin <= %(end_date)s

UNION ALL

SELECT 'indicator' as data_type, ticker, timeframe, begin, 0.0, 0.0, 0.0, 0.0, 0.0, indicator_key, value_key, value
FROM trader.candles_indicators FINAL
PREWHERE ticker = %(ticker)s AND timeframe = %(timeframe)s
WHERE begin >= %(start_date)s
  AND begin <= %(end_date)s
  AND (indicator_key, value_key) IN %(indicator_key_pairs)s
"""

# Проверка полноты данных индикаторов с PREWHERE оптимизацией
VERIFY_DATA_COMPLETENESS_QUERY = """
SELECT
    indicator_key,
    count(DISTINCT begin) as covered_candles,
    count(*) as total_records,
    count(DISTINCT (begin, value_key)) as unique_combinations
FROM trader.candles_indicators FINAL
PREWHERE ticker = %(ticker)s AND timeframe = %(timeframe)s
WHERE begin >= %(start_date)s
  AND begin <= %(end_date)s
  AND indicator_key IN %(indicator_base_keys)s
GROUP BY indicator_key
"""

# Подсчет требуемых свечей с PREWHERE оптимизацией
GET_REQUIRED_CANDLES_COUNT_QUERY = """
SELECT count() as total_candles
FROM trader.candles_base
PREWHERE ticker = %(ticker)s AND timeframe = %(timeframe)s
WHERE begin >= %(start_date)s AND begin <= %(end_date)s
"""


class ClickHouseRepository:
    """
    Асинхронный репозиторий для взаимодействия с ClickHouse.

    Основная задача: эффективное извлечение исторических данных для бэктестов.
    Все методы принимают async client из pool для параллельной обработки.
    """

    async def get_missing_indicator_periods(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        required_indicators: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """
        Оптимизированная проверка полноты данных индикаторов.

        Использует tenacity для автоматических повторов при сетевых ошибках:
        - 3 попытки с экспоненциальной задержкой (1s, 2s, 4s)
        - Retry только на ClickHouseError и asyncio.TimeoutError

        Args:
            client: Async ClickHouse client из pool.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Начальная дата периода (ISO format).
            end_date: Конечная дата периода (ISO format).
            required_indicators: Список пар (indicator_key, value_key).

        Returns:
            Список недостающих индикаторов (пары indicator_key, value_key).
        """
        if not required_indicators:
            return []

        unique_base_keys = sorted(
            list({base_key for base_key, value_key in required_indicators})
        )

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (ClickHouseError, asyncio.TimeoutError)
            ),
            reraise=True,
        ):
            with attempt:
                return await self._do_get_missing_indicator_periods(
                    client,
                    ticker,
                    timeframe,
                    start_date,
                    end_date,
                    unique_base_keys,
                    required_indicators,
                )

    async def _do_get_missing_indicator_periods(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        unique_base_keys: list[str],
        required_indicators: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """
        Координатор проверки полноты данных индикаторов.

        Разбит на несколько методов для лучшей читаемости:
        1. Валидация параметров
        2. Получение количества требуемых свечей
        3. Проверка покрытия индикаторов
        4. Построение списка недостающих пар

        Args:
            client: Async ClickHouse client.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: ISO format строка.
            end_date: ISO format строка.
            unique_base_keys: Уникальные base_key индикаторов.
            required_indicators: Полный список требуемых пар.

        Returns:
            Список недостающих пар (indicator_key, value_key).
        """
        try:
            # 1. Валидация входных параметров
            self._validate_request_params(
                ticker, timeframe, start_date, end_date
            )

            logger.info(
                "clickhouse.checking_data_completeness",
                ticker=ticker,
                timeframe=timeframe,
                indicators_count=len(unique_base_keys),
            )

            # 2. Получаем количество требуемых свечей
            required_candles = await self._get_required_candles_count(
                client, ticker, timeframe, start_date, end_date
            )

            if required_candles == 0:
                logger.warning(
                    "clickhouse.no_base_candles_found",
                    ticker=ticker,
                    timeframe=timeframe,
                )
                return required_indicators

            # 3. Проверяем покрытие индикаторов
            incomplete_base_keys = await self._check_indicators_coverage(
                client,
                ticker,
                timeframe,
                start_date,
                end_date,
                unique_base_keys,
                required_candles,
            )

            # 4. Формируем список недостающих пар
            if incomplete_base_keys:
                missing_pairs = self._build_missing_pairs_list(
                    required_indicators,
                    incomplete_base_keys,
                    ticker,
                    timeframe,
                )
                return missing_pairs

            logger.info(
                "clickhouse.data_completeness_check_passed",
                ticker=ticker,
                timeframe=timeframe,
            )
            return []

        except Exception as exc:
            logger.exception(
                "clickhouse.data_completeness_check_failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(exc),
            )
            raise

    def _validate_request_params(
        self,
        ticker: str,
        timeframe: str,
        start_date: str,
        end_date: str,
    ) -> None:
        """
        Валидирует входные параметры запроса.

        Args:
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Начальная дата (ISO format).
            end_date: Конечная дата (ISO format).

        Raises:
            ValueError: При невалидных параметрах.
        """
        if not ticker or not ticker.strip():
            raise ValueError("Ticker cannot be empty")

        if not timeframe or not timeframe.strip():
            raise ValueError("Timeframe cannot be empty")

        # Проверка порядка дат
        try:
            start_dt = (
                datetime.fromisoformat(start_date)
                if isinstance(start_date, str)
                else start_date
            )
            end_dt = (
                datetime.fromisoformat(end_date)
                if isinstance(end_date, str)
                else end_date
            )

            if start_dt >= end_dt:
                raise ValueError(
                    f"Start date must be before end date. "
                    f"Start: {start_date}, End: {end_date}"
                )
        except ValueError as e:
            if "fromisoformat" in str(e):
                raise ValueError(f"Invalid date format: {e}") from e
            raise

    async def _get_required_candles_count(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: str,
        end_date: str,
    ) -> int:
        """
        Получает количество требуемых свечей для периода.

        Args:
            client: Async ClickHouse client.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Начальная дата.
            end_date: Конечная дата.

        Returns:
            Количество свечей в периоде.
        """
        params = {
            "ticker": ticker,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
        }

        result = await client.query(
            GET_REQUIRED_CANDLES_COUNT_QUERY, parameters=params
        )

        return result.result_rows[0][0] if result.result_rows else 0

    async def _check_indicators_coverage(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        unique_base_keys: list[str],
        required_candles: int,
    ) -> set[str]:
        """
        Проверяет покрытие индикаторов и находит проблемные.

        Индикатор считается проблемным если:
        1. Имеет дубликаты (total_records > unique_combinations)
        2. Неполное покрытие (covered_candles < required_candles)
        3. Полностью отсутствует в БД

        Args:
            client: Async ClickHouse client.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Начальная дата.
            end_date: Конечная дата.
            unique_base_keys: Список уникальных base_key.
            required_candles: Ожидаемое количество свечей.

        Returns:
            Множество base_key проблемных индикаторов.
        """
        params = {
            "ticker": ticker,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "indicator_base_keys": unique_base_keys,
        }

        result = await client.query(
            VERIFY_DATA_COMPLETENESS_QUERY, parameters=params
        )

        incomplete_base_keys = set()
        found_indicators = set()

        # Анализируем результаты по каждому индикатору
        for row in result.result_rows:
            indicator_key = row[0]
            covered_candles = row[1]
            total_records = row[2]
            unique_combinations = row[3]

            found_indicators.add(indicator_key)

            has_duplicates = total_records > unique_combinations
            is_incomplete = covered_candles < required_candles

            if has_duplicates:
                logger.warning(
                    "clickhouse.indicator_has_duplicates",
                    indicator_key=indicator_key,
                    ticker=ticker,
                    timeframe=timeframe,
                    total_records=total_records,
                    unique_combinations=unique_combinations,
                )
                incomplete_base_keys.add(indicator_key)
            elif is_incomplete:
                logger.warning(
                    "clickhouse.indicator_incomplete",
                    indicator_key=indicator_key,
                    ticker=ticker,
                    timeframe=timeframe,
                    covered_candles=covered_candles,
                    required_candles=required_candles,
                )
                incomplete_base_keys.add(indicator_key)

        # Проверяем полностью отсутствующие индикаторы
        missing_indicators = set(unique_base_keys) - found_indicators
        for indicator_key in missing_indicators:
            logger.warning(
                "clickhouse.indicator_missing",
                indicator_key=indicator_key,
                ticker=ticker,
                timeframe=timeframe,
            )
            incomplete_base_keys.add(indicator_key)

        return incomplete_base_keys

    def _build_missing_pairs_list(
        self,
        required_indicators: list[tuple[str, str]],
        incomplete_base_keys: set[str],
        ticker: str,
        timeframe: str,
    ) -> list[tuple[str, str]]:
        """
        Формирует список недостающих пар индикаторов.

        Возвращает все пары (base_key, value_key), где base_key
        входит в список проблемных индикаторов.

        Args:
            required_indicators: Все требуемые пары.
            incomplete_base_keys: Множество проблемных base_key.
            ticker: Тикер (для логирования).
            timeframe: Таймфрейм (для логирования).

        Returns:
            Список недостающих пар (indicator_key, value_key).
        """
        logger.warning(
            "clickhouse.incomplete_indicators_detected",
            ticker=ticker,
            timeframe=timeframe,
            indicators=list(incomplete_base_keys),
        )

        # Возвращаем все компоненты проблемных индикаторов
        missing_pairs = [
            pair
            for pair in required_indicators
            if pair[0] in incomplete_base_keys
        ]

        return missing_pairs

    async def fetch_data_for_backtest(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        indicator_key_pairs: list[tuple[str, str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Извлекает все необходимые данные для бэктеста.

        Возвращает два отдельных списка: базовые свечи и индикаторы.

        Использует tenacity для автоматических повторов при сетевых ошибках:
        - 3 попытки с экспоненциальной задержкой (1s, 2s, 4s)
        - Retry только на ClickHouseError и asyncio.TimeoutError

        Args:
            client: Async ClickHouse client из pool.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Начальная дата (ISO format или datetime).
            end_date: Конечная дата (ISO format или datetime).
            indicator_key_pairs: Список пар (indicator_key, value_key).

        Returns:
            Tuple (base_candles, indicators_data).
        """
        if not indicator_key_pairs:
            indicator_key_pairs = [CLICKHOUSE_DUMMY_INDICATOR_PAIR]

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(
                (ClickHouseError, asyncio.TimeoutError)
            ),
            reraise=True,
        ):
            with attempt:
                return await self._do_fetch_data_for_backtest(
                    client,
                    ticker,
                    timeframe,
                    start_date,
                    end_date,
                    indicator_key_pairs,
                )

    async def _do_fetch_data_for_backtest(
        self,
        client: AsyncClient,
        ticker: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        indicator_key_pairs: list[tuple[str, str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Внутренний метод для извлечения данных бэктеста.

        Выделен для применения retry логики через AsyncRetrying.

        Args:
            client: Async ClickHouse client.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            start_date: Начальная дата.
            end_date: Конечная дата.
            indicator_key_pairs: Список пар индикаторов.

        Returns:
            Tuple (base_candles, indicators_data).
        """
        params = {
            "ticker": ticker,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "indicator_key_pairs": indicator_key_pairs,
        }

        base_candles = []
        indicators_data = []

        try:
            logger.info(
                "clickhouse.loading_backtest_data",
                ticker=ticker,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
            )

            query_start = time.time()
            result = await client.query(
                GET_BACKTEST_DATA_QUERY, parameters=params
            )
            query_elapsed_ms = (time.time() - query_start) * 1000

            # Разделяем результат на два списка
            for row in result.named_results():
                if row["data_type"] == "candle":
                    base_candles.append(row)
                else:
                    indicators_data.append(row)

            logger.info(
                "clickhouse.query_completed",
                query_type="fetch_backtest_data",
                elapsed_ms=round(query_elapsed_ms, 2),
                candles_count=len(base_candles),
                indicators_count=len(indicators_data),
                total_rows=len(base_candles) + len(indicators_data),
            )

            # Warning для медленных запросов
            if query_elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
                logger.warning(
                    "clickhouse.slow_query_detected",
                    elapsed_ms=round(query_elapsed_ms, 2),
                    threshold_ms=SLOW_QUERY_THRESHOLD_MS,
                    ticker=ticker,
                    timeframe=timeframe,
                )
            return base_candles, indicators_data

        except Exception as exc:
            logger.exception(
                "clickhouse.backtest_data_load_failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(exc),
            )
            raise
