"""
CRUD операции для работы с ClickHouse - проверка наличия исторических данных.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from clickhouse_connect.driver.client import Client as ClickHouseClient
from tradeforge_logger import get_logger

from app.services.indicator_lookback_calculator import (
    calculate_max_lookback_from_definitions,
    extract_indicator_definitions_from_strategy,
)

log = get_logger(__name__)


async def check_data_availability(
    clickhouse_client: ClickHouseClient,
    data_requirements: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """
    Проверяет наличие данных в ClickHouse для списка требований.

    Выполняет ОДИН запрос для всех комбинаций (ticker, timeframe, period).

    Args:
        clickhouse_client: Клиент ClickHouse
        data_requirements: Список требований в формате:
            [
                {
                    "ticker": "SBER",
                    "timeframe": "1h",
                    "start_date": "2023-01-01T00:00:00+03:00",
                    "end_date": "2023-12-31T23:59:59+03:00"
                },
                ...
            ]

    Returns:
        Словарь с результатами проверки:
        {
            ("SBER", "1h", "2023-01-01", "2023-12-31"): {
                "has_data": True,
                "first_candle": "2023-01-01T10:00:00",
                "last_candle": "2023-12-31T18:00:00",
                "candles_count": 2520
            },
            ("NVTK", "1h", "2023-01-01", "2023-12-31"): {
                "has_data": False,
                "first_candle": None,
                "last_candle": None,
                "candles_count": 0
            }
        }
    """
    if not data_requirements:
        return {}

    try:
        # Строим UNION ALL запрос для всех комбинаций
        queries = []
        for req in data_requirements:
            ticker = req["ticker"]
            timeframe = req["timeframe"]
            start_date = _format_datetime_for_clickhouse(req["start_date"])
            end_date = _format_datetime_for_clickhouse(req["end_date"])

            log.debug(
                "clickhouse.date.formatting",
                ticker=ticker,
                timeframe=timeframe,
                original_start=req["start_date"],
                original_end=req["end_date"],
                formatted_start=start_date,
                formatted_end=end_date,
            )

            # Извлекаем только дату для ключа результата
            start_date_key = (
                start_date.split("T")[0]
                if "T" in start_date
                else start_date.split(" ")[0]
            )
            end_date_key = (
                end_date.split("T")[0]
                if "T" in end_date
                else end_date.split(" ")[0]
            )

            # Используем подзапрос для корректного подсчета
            queries.append(
                f"""
                SELECT
                    '{ticker}' AS ticker,
                    '{timeframe}' AS timeframe,
                    '{start_date_key}' AS start_date_key,
                    '{end_date_key}' AS end_date_key,
                    MIN(filtered.begin) AS first_candle,
                    MAX(filtered.begin) AS last_candle,
                    COUNT(*) AS candles_count
                FROM (
                    SELECT begin
                    FROM trader.candles_base
                    WHERE ticker = '{ticker}'
                      AND timeframe = '{timeframe}'
                      AND begin >= toDateTime('{start_date}')
                      AND begin <= toDateTime('{end_date}')
                ) AS filtered
            """
            )

        full_query = " UNION ALL ".join(queries)

        log.info(
            "clickhouse.data.check.started",
            requirements_count=len(data_requirements),
        )

        # Выполняем запрос (синхронный метод clickhouse_connect)
        result = clickhouse_client.query(full_query)

        # Обрабатываем результат
        availability = {}
        for row in result.result_rows:
            ticker = row[0]
            timeframe = row[1]
            start_date_key = row[2]
            end_date_key = row[3]
            first_candle = row[4]
            last_candle = row[5]
            candles_count = row[6]

            key = (ticker, timeframe, start_date_key, end_date_key)
            has_data = candles_count > 0

            availability[key] = {
                "has_data": has_data,
                "first_candle": first_candle,
                "last_candle": last_candle,
                "candles_count": candles_count,
            }

            log.debug(
                "clickhouse.data.check.result",
                ticker=ticker,
                timeframe=timeframe,
                period=f"{start_date_key} - {end_date_key}",
                has_data=has_data,
                candles_count=candles_count,
            )

        return availability

    except Exception as e:
        log.error(
            "clickhouse.data.check.error",
            error=str(e),
            requirements_count=len(data_requirements),
            exc_info=True,
        )
        # В случае ошибки возвращаем пустой результат
        # Лучше не блокировать создание бэктестов из-за проблем с ClickHouse
        return {}


async def check_data_availability_with_lookback(
    clickhouse_client: ClickHouseClient,
    ticker: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    strategy_definition: dict[str, Any],
) -> dict[str, Any]:
    """
    Проверяет достаточность данных с учетом lookback периода индикаторов.

    Args:
        clickhouse_client: Клиент ClickHouse
        ticker: Тикер
        timeframe: Таймфрейм
        start_date: Дата начала периода бэктеста
        end_date: Дата окончания периода бэктеста
        strategy_definition: AST определение стратегии

    Returns:
        Словарь с результатами проверки:
        {
            "has_sufficient_data": True/False,
            "error_message": "..." (если has_sufficient_data=False),
            "max_lookback": 100,
            "period_first_candle": "2024-01-03T10:00:00",
            "period_last_candle": "2024-12-31T18:00:00",
            "lookback_candles_count": 150
        }
    """
    try:
        # 1. Извлекаем индикаторы из стратегии
        indicator_defs = extract_indicator_definitions_from_strategy(
            strategy_definition
        )

        # 2. Рассчитываем максимальный lookback
        max_lookback = calculate_max_lookback_from_definitions(indicator_defs)

        log.info(
            "clickhouse.lookback.check.started",
            ticker=ticker,
            timeframe=timeframe,
            period=f"{start_date} - {end_date}",
            indicators_count=len(indicator_defs),
            max_lookback=max_lookback,
        )

        # Форматируем даты для ClickHouse
        formatted_start = _format_datetime_for_clickhouse(start_date)
        formatted_end = _format_datetime_for_clickhouse(end_date)

        # 3. ЗАПРОС 1: Проверяем покрытие периода (границы)
        period_query = f"""
            SELECT
                MIN(begin) AS first_candle,
                MAX(begin) AS last_candle
            FROM trader.candles_base
            WHERE ticker = '{ticker}'
              AND timeframe = '{timeframe}'
              AND begin >= toDateTime('{formatted_start}')
              AND begin <= toDateTime('{formatted_end}')
        """

        log.debug(
            "clickhouse.lookback.period.check.started",
            ticker=ticker,
            timeframe=timeframe,
        )

        period_result = clickhouse_client.query(period_query)

        if (
            not period_result.result_rows
            or len(period_result.result_rows) == 0
        ):
            # Нет данных вообще
            return {
                "has_sufficient_data": False,
                "error_message": f"Нет исторических данных для тикера '{ticker}' ({timeframe}) за период {start_date} - {end_date}",
                "max_lookback": max_lookback,
                "period_first_candle": None,
                "period_last_candle": None,
                "lookback_candles_count": 0,
            }

        first_candle = period_result.result_rows[0][0]
        last_candle = period_result.result_rows[0][1]

        # Проверяем что границы покрыты
        if first_candle is None or last_candle is None:
            return {
                "has_sufficient_data": False,
                "error_message": f"Нет исторических данных для тикера '{ticker}' ({timeframe}) за период {start_date} - {end_date}",
                "max_lookback": max_lookback,
                "period_first_candle": None,
                "period_last_candle": None,
                "lookback_candles_count": 0,
            }

        # 4. ЗАПРОС 2: Проверяем количество свечей ДО start_date для lookback
        # Это ГЛАВНАЯ проверка - если есть lookback, то начало периода покрыто благодаря консистентности
        lookback_query = f"""
            SELECT COUNT(*) AS lookback_count
            FROM (
                SELECT begin
                FROM trader.candles_base
                WHERE ticker = '{ticker}'
                  AND timeframe = '{timeframe}'
                  AND begin < toDateTime('{formatted_start}')
                ORDER BY begin DESC
                LIMIT {max_lookback}
            ) AS lookback_candles
        """

        log.debug(
            "clickhouse.lookback.candles.check.started",
            ticker=ticker,
            timeframe=timeframe,
            max_lookback=max_lookback,
        )

        lookback_result = clickhouse_client.query(lookback_query)
        lookback_count = (
            lookback_result.result_rows[0][0]
            if lookback_result.result_rows
            else 0
        )

        # Проверка достаточности lookback
        if lookback_count < max_lookback:
            # Запрашиваем самую первую доступную свечу для этого тикера/таймфрейма
            # чтобы показать пользователю с какой даты у нас есть данные
            # Используем toTimeZone() чтобы ClickHouse вернул время в московском часовом поясе
            first_available_query = f"""
                SELECT toTimeZone(MIN(begin), 'Europe/Moscow') AS first_available
                FROM trader.candles_base
                WHERE ticker = '{ticker}'
                  AND timeframe = '{timeframe}'
            """
            first_available_result = clickhouse_client.query(
                first_available_query
            )
            first_available = (
                first_available_result.result_rows[0][0]
                if first_available_result.result_rows
                else None
            )

            # Формируем информативное сообщение
            if first_available is not None and first_available.year > 1970:
                first_candle_info = f"Данные доступны с {first_available}. "
            else:
                first_candle_info = (
                    "Нет исторических данных для данного тикера и таймфрейма. "
                )

            error_message = (
                f"Недостаточно данных для прогрева индикаторов. "
                f"Для стратегии требуется минимум {max_lookback} свечей до начала периода ({start_date}), "
                f"доступно: {lookback_count}. "
                f"{first_candle_info}"
                f"Попробуйте выбрать более поздний период начала."
            )

            await log.awarning(
                "clickhouse.lookback.insufficient",
                ticker=ticker,
                timeframe=timeframe,
                required_lookback=max_lookback,
                available_lookback=lookback_count,
                first_available_candle=(
                    str(first_available) if first_available else None
                ),
            )

            return {
                "has_sufficient_data": False,
                "error_message": error_message,
                "max_lookback": max_lookback,
                "period_first_candle": str(first_candle),
                "period_last_candle": str(last_candle),
                "lookback_candles_count": lookback_count,
            }

        # Все проверки пройдены
        log.info(
            "clickhouse.lookback.check.success",
            ticker=ticker,
            timeframe=timeframe,
            period_first_candle=str(first_candle),
            period_last_candle=str(last_candle),
            lookback_count=lookback_count,
            max_lookback=max_lookback,
        )

        return {
            "has_sufficient_data": True,
            "error_message": None,
            "max_lookback": max_lookback,
            "period_first_candle": str(first_candle),
            "period_last_candle": str(last_candle),
            "lookback_candles_count": lookback_count,
        }

    except Exception as e:
        log.error(
            "clickhouse.lookback.check.error",
            ticker=ticker,
            timeframe=timeframe,
            error=str(e),
            exc_info=True,
        )
        # В случае ошибки возвращаем консервативный результат
        return {
            "has_sufficient_data": True,  # Не блокируем в случае ошибки
            "error_message": None,
            "max_lookback": 0,
            "period_first_candle": None,
            "period_last_candle": None,
            "lookback_candles_count": 0,
        }


def _format_datetime_for_clickhouse(date_str: str) -> str:
    """
    Форматирует дату для использования в ClickHouse запросе.

    Args:
        date_str: Дата в ISO формате (с timezone или без)

    Returns:
        Дата в формате для ClickHouse: 'YYYY-MM-DD HH:MM:SS' (в московском времени)
    """
    try:
        moscow_tz = ZoneInfo("Europe/Moscow")

        # Парсим дату
        if "T" in date_str:
            # ISO формат с временем
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            # Конвертируем в московское время
            if dt.tzinfo is not None:
                dt_moscow = dt.astimezone(moscow_tz)
            else:
                dt_moscow = dt.replace(tzinfo=moscow_tz)
        else:
            # Только дата - парсим как naive datetime и сразу присваиваем Moscow timezone
            # Это важно, чтобы правильно учитывались исторические переходы на летнее/зимнее время
            naive_dt = datetime.fromisoformat(date_str + "T00:00:00")
            dt_moscow = naive_dt.replace(tzinfo=moscow_tz)

        # Форматируем для ClickHouse (без timezone, так как данные уже в MSK)
        return dt_moscow.strftime("%Y-%m-%d %H:%M:%S")

    except Exception:
        # Если не можем распарсить, возвращаем как есть
        return date_str
