"""
Модуль для работы с данными.

Содержит компоненты для подготовки и управления данными:
- prepare_dataframe: Преобразование данных из ClickHouse в DataFrame
- IndicatorResolver: Проверка и запрос расчета индикаторов
"""

from __future__ import annotations

from .indicator_resolver import IndicatorResolver
from .preparer import prepare_dataframe

__all__ = [
    "IndicatorResolver",
    "prepare_dataframe",
]
