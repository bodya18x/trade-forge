"""
Утилиты для Trading Engine.

Содержит вспомогательные функции общего назначения.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


def sanitize_json(obj: Any) -> Any:
    """
    Рекурсивно заменяет NaN и Infinity на None в структурах данных.

    JSON не поддерживает NaN и Infinity, поэтому эти значения должны быть
    заменены на None перед сериализацией.

    Args:
        obj: Любой Python объект (dict, list, float, и т.д.).

    Returns:
        Санитизированная копия объекта с NaN/Inf -> None.

    Examples:
        >>> sanitize_json({"a": float('nan'), "b": float('inf')})
        {"a": None, "b": None}

        >>> sanitize_json([1.5, float('nan'), 3.0])
        [1.5, None, 3.0]
    """
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def convert_to_moscow_tz(dt: datetime | None) -> datetime | None:
    """
    Конвертирует datetime в московское время если нужно.

    Если datetime уже в московском времени или не имеет timezone - возвращает как есть.
    Если datetime в другом timezone - конвертирует в Europe/Moscow.

    Args:
        dt: Datetime объект для конвертации или None.

    Returns:
        Datetime в московском времени или None если входной None.

    Examples:
        >>> from datetime import datetime
        >>> from zoneinfo import ZoneInfo
        >>> utc_dt = datetime(2025, 1, 1, 12, 0, tzinfo=ZoneInfo("UTC"))
        >>> moscow_dt = convert_to_moscow_tz(utc_dt)
        >>> print(moscow_dt.tzinfo)
        Europe/Moscow

        >>> moscow_dt = datetime(2025, 1, 1, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        >>> result = convert_to_moscow_tz(moscow_dt)
        >>> assert result == moscow_dt  # Уже в московском времени
    """
    if dt is None:
        return None

    if not hasattr(dt, "tzinfo") or dt.tzinfo is None:
        return dt

    moscow_tz = ZoneInfo("Europe/Moscow")

    if str(dt.tzinfo) == "Europe/Moscow":
        return dt

    return dt.astimezone(moscow_tz)
