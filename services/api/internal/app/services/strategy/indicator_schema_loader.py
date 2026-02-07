"""
Загрузчик схем индикаторов из indicators.json.

Предоставляет доступ к метаданным индикаторов для валидации.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradeforge_logger import get_logger

logger = get_logger(__name__)


class IndicatorSchema:
    """Схема одного индикатора."""

    def __init__(self, data: dict[str, Any]):
        """
        Инициализирует схему индикатора.

        Args:
            data: Словарь с данными индикатора из indicators.json
        """
        self.name: str = data["name"]
        self.display_name: str = data["display_name"]
        self.key_template: str = data["key_template"]
        self.parameters_schema: dict[str, Any] = data["parameters_schema"]
        self.output_schema: dict[str, Any] = data["output_schema"]

    def get_parameter_type(self, param_name: str) -> str | None:
        """
        Возвращает тип параметра.

        Args:
            param_name: Имя параметра

        Returns:
            Тип параметра ("integer", "number", "boolean", "string") или None
        """
        props = self.parameters_schema.get("properties", {})
        param = props.get(param_name)
        return param.get("type") if param else None

    def get_parameter_range(self, param_name: str) -> tuple[Any, Any] | None:
        """
        Возвращает допустимый диапазон значений параметра.

        Args:
            param_name: Имя параметра

        Returns:
            Кортеж (minimum, maximum) или None
        """
        props = self.parameters_schema.get("properties", {})
        param = props.get(param_name)
        if not param:
            return None

        minimum = param.get("minimum")
        maximum = param.get("maximum")

        if minimum is not None or maximum is not None:
            return (minimum, maximum)

        return None

    def get_output_keys(self) -> list[str]:
        """
        Возвращает список всех возможных выходных ключей индикатора.

        Returns:
            Список имен выходных значений (например, ["value"] или ["macd", "signal", "hist"])
        """
        return list(self.output_schema.get("properties", {}).keys())


class IndicatorSchemaLoader:
    """Загрузчик схем индикаторов из indicators.json."""

    _instance: IndicatorSchemaLoader | None = None
    _schemas: dict[str, IndicatorSchema] | None = None

    def __new__(cls) -> IndicatorSchemaLoader:
        """Singleton паттерн для переиспользования загруженных схем."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Инициализирует загрузчик (загружает схемы при первом вызове)."""
        if self._schemas is None:
            self._load_schemas()

    def _load_schemas(self) -> None:
        """Загружает схемы из indicators.json."""
        indicators_file = Path("/app/data/indicators.json")

        try:
            if not indicators_file.exists():
                logger.error(
                    "indicator_schema_loader.file_not_found",
                    path=str(indicators_file),
                )
                self._schemas = {}
                return

            with open(indicators_file, "r", encoding="utf-8") as f:
                indicators_data = json.load(f)

            self._schemas = {}
            for indicator_data in indicators_data:
                schema = IndicatorSchema(indicator_data)
                self._schemas[schema.name] = schema

            logger.info(
                "indicator_schema_loader.schemas_loaded",
                count=len(self._schemas),
            )

        except Exception as e:
            logger.exception(
                "indicator_schema_loader.load_failed",
                error=str(e),
            )
            self._schemas = {}

    def get_schema(self, indicator_name: str) -> IndicatorSchema | None:
        """
        Возвращает схему индикатора по имени.

        Args:
            indicator_name: Имя индикатора (например, "sma", "supertrend")

        Returns:
            Схема индикатора или None если не найдена
        """
        return self._schemas.get(indicator_name) if self._schemas else None

    def get_all_indicator_names(self) -> list[str]:
        """
        Возвращает список всех доступных индикаторов.

        Returns:
            Список имен индикаторов
        """
        return list(self._schemas.keys()) if self._schemas else []
