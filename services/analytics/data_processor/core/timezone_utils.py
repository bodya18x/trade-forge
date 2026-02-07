"""
Timezone utilities for data_processor service.

Единая стратегия работы с datetime и timezone:
- ВСЕ datetime в системе работают в московском часовом поясе (Europe/Moscow)
- ClickHouse хранит DateTime64(3, 'Europe/Moscow') с timezone информацией
- При записи в ClickHouse передаем timezone-aware datetime (драйвер правильно обрабатывает TZ)
- При чтении из ClickHouse добавляем timezone если его нет

Это централизованное место для всех операций с timezone, чтобы избежать ошибок
и несогласованности в разных частях кода.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
UTC_TZ = ZoneInfo("UTC")


def ensure_moscow_tz(dt: datetime) -> datetime:
    """
    Гарантирует что datetime в московском timezone (aware).

    Args:
        dt: Datetime (может быть naive или aware в любой timezone).

    Returns:
        Datetime в московском timezone (aware).

    Example:
        >>> naive_dt = datetime(2024, 1, 15, 12, 0, 0)
        >>> aware_dt = ensure_moscow_tz(naive_dt)
        >>> aware_dt.tzinfo
        ZoneInfo(key='Europe/Moscow')
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MOSCOW_TZ)
    return dt.astimezone(MOSCOW_TZ)


def to_clickhouse(dt: datetime) -> datetime:
    """
    Подготавливает datetime для INSERT операций в ClickHouse (PyArrow).

    ClickHouse колонки типа DateTime64(3, 'Europe/Moscow') работают так:
    - PyArrow конвертирует timezone-aware datetime в UTC при сериализации
    - ClickHouse получает UTC значение и добавляет +3 часа согласно типу колонки
    - Результат: корректное московское время

    Пример:
    - Python: 12:00 MSK (timezone-aware)
    - PyArrow сериализует: 09:00 UTC
    - ClickHouse интерпретирует: 09:00 UTC + 3h = 12:00 MSK ✅

    Args:
        dt: Datetime (любой timezone или naive).

    Returns:
        Timezone-aware datetime в московском времени для PyArrow INSERT.

    Example:
        >>> aware_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=MOSCOW_TZ)
        >>> moscow_dt = to_clickhouse(aware_dt)
        >>> moscow_dt.tzinfo
        ZoneInfo(key='Europe/Moscow')
    """
    return ensure_moscow_tz(dt)


def to_clickhouse_query(dt: datetime) -> datetime:
    """
    Подготавливает datetime для WHERE параметров в ClickHouse запросах.

    При использовании параметров в SQL запросах:
    - Драйвер clickhouse-connect конвертирует timezone-aware datetime в UTC
    - ClickHouse сравнивает UTC значение с MSK колонкой
    - Результат: потеря 3 часов ❌

    Пример проблемы с timezone-aware:
    - Python: 2025-11-28 23:59:59+03:00 (Moscow)
    - Драйвер конвертирует: 2025-11-28 20:59:59 UTC
    - WHERE begin <= '2025-11-28 20:59:59'
    - Пропускаются свечи с 21:00 до 23:59 ❌

    Решение: Передаем naive datetime, который ClickHouse интерпретирует
    как Moscow TZ согласно определению колонки.

    Args:
        dt: Datetime (любой timezone или naive).

    Returns:
        Naive datetime в московском времени (без tzinfo).

    Example:
        >>> aware_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=MOSCOW_TZ)
        >>> moscow_dt = to_clickhouse_query(aware_dt)
        >>> moscow_dt.tzinfo is None
        True
        >>> moscow_dt
        datetime(2024, 1, 15, 12, 0, 0)
    """
    moscow_dt = ensure_moscow_tz(dt)
    return moscow_dt.replace(tzinfo=None)


def from_clickhouse(dt: datetime) -> datetime:
    """
    Конвертирует datetime из ClickHouse в timezone-aware.

    ClickHouse возвращает naive datetime, который нужно интерпретировать
    как московское время.

    Args:
        dt: Naive datetime из ClickHouse.

    Returns:
        Datetime с московским timezone (aware).

    Example:
        >>> naive_dt = datetime(2024, 1, 15, 12, 0, 0)
        >>> aware_dt = from_clickhouse(naive_dt)
        >>> aware_dt.tzinfo
        ZoneInfo(key='Europe/Moscow')
    """
    if dt.tzinfo is not None:
        return dt.astimezone(MOSCOW_TZ)
    return dt.replace(tzinfo=MOSCOW_TZ)
