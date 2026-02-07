"""
Модуль управления индикаторами Trade Forge.

Этот модуль предоставляет инструменты для:
- Валидации JSON-описаний индикаторов
- Синхронизации индикаторов с базой данных
- Генерации ключей индикаторов
- Управления метаданными индикаторов для фронтенда
"""

from .manager import IndicatorsCLI, IndicatorsManager
from .schemas import (
    ChartType,
    IndicatorCategory,
    IndicatorComplexity,
    IndicatorKeyGenerator,
    IndicatorValidationError,
    IndicatorValidator,
    SystemIndicatorDefinition,
    SystemIndicatorsList,
)

__version__ = "1.0.0"

__all__ = [
    # Manager classes
    "IndicatorsManager",
    "IndicatorsCLI",
    # Schema classes and enums
    "IndicatorCategory",
    "IndicatorComplexity",
    "ChartType",
    "SystemIndicatorDefinition",
    "SystemIndicatorsList",
    # Utility classes
    "IndicatorKeyGenerator",
    "IndicatorValidator",
    "IndicatorValidationError",
]
