"""
Валидатор ключей индикаторов в стратегиях.

Проверяет корректность формата ключей индикаторов используя схемы из indicators.json.
"""

from __future__ import annotations

import re
from typing import Any

from tradeforge_logger import get_logger
from tradeforge_schemas import ValidationErrorDetail

from .indicator_schema_loader import IndicatorSchemaLoader

logger = get_logger(__name__)


def normalize_strategy_definition(
    definition_dict: dict, validator: "IndicatorKeyValidator"
) -> dict:
    """
    Рекурсивно нормализует все ключи индикаторов в definition стратегии.

    Заменяет .0 на целые числа для integer параметров во всех ключах.

    Args:
        definition_dict: Словарь с definition стратегии
        validator: Экземпляр IndicatorKeyValidator для нормализации ключей

    Returns:
        Нормализованный definition
    """

    def normalize_recursive(obj):
        if isinstance(obj, dict):
            normalized = {}
            for k, v in obj.items():
                if k in ("key", "indicator_key") and isinstance(v, str):
                    # Это ключ индикатора, нормализуем его
                    normalized[k] = validator.normalize_indicator_key(v)
                else:
                    normalized[k] = normalize_recursive(v)
            return normalized
        elif isinstance(obj, list):
            return [normalize_recursive(item) for item in obj]
        else:
            return obj

    return normalize_recursive(definition_dict)


class IndicatorKeyValidator:
    """
    Валидатор ключей индикаторов.

    Проверяет что ключи индикаторов в стратегиях:
    - Имеют правильный формат
    - Содержат корректные типы параметров (integer НЕ может содержать .0 в ключе)
    - Значения параметров в допустимых диапазонах
    - Пропускает базовые OHLCV ключи (open, high, low, close, volume)

    Примеры:
    - sma_timeperiod_14_value ✓
    - sma_timeperiod_14.0_value ✗ (должно быть 14, а не 14.0)
    - supertrend_length_10_multiplier_3.0_direction ✓ (3.0 - float параметр)
    """

    # Базовые OHLCV ключи (не индикаторы)
    OHLCV_KEYS = {"open", "high", "low", "close", "volume"}

    # Суффиксы значений индикаторов
    VALUE_SUFFIXES = {
        "value",
        "direction",
        "long",
        "short",
        "trend",
        "macd",
        "signal",
        "hist",
        "k",
        "d",
        "upper",
        "middle",
        "lower",
    }

    def __init__(self):
        """Инициализирует валидатор."""
        self.schema_loader = IndicatorSchemaLoader()

    def normalize_indicator_key(self, key: str) -> str:
        """
        Нормализует ключ индикатора, заменяя .0 на целые числа для integer параметров.

        Args:
            key: Ключ индикатора (например, "supertrend_length_10.0_multiplier_3.0_direction")

        Returns:
            Нормализованный ключ (например, "supertrend_length_10_multiplier_3.0_direction")
        """
        # Пропускаем OHLCV ключи
        if key in self.OHLCV_KEYS:
            return key

        # Парсим ключ
        parsed = self._parse_indicator_key(key)
        if not parsed:
            return key

        # Получаем схему
        schema = self.schema_loader.get_schema(parsed["name"])
        if not schema:
            return key

        # Нормализуем параметры
        normalized_key = key
        for param_name, param_value in parsed["params"].items():
            expected_type = schema.get_parameter_type(param_name)
            if expected_type == "integer" and isinstance(param_value, float):
                if param_value == int(param_value):
                    # Заменяем в ключе .0 на целое число
                    normalized_key = normalized_key.replace(
                        f"_{param_value}_", f"_{int(param_value)}_"
                    ).replace(f"_{param_value}", f"_{int(param_value)}")

        return normalized_key

    def validate_indicator_keys(
        self, indicator_keys: set[str]
    ) -> list[ValidationErrorDetail]:
        """
        Валидирует набор ключей индикаторов.

        Args:
            indicator_keys: Множество полных ключей индикаторов из стратегии

        Returns:
            Список ошибок валидации (пустой если все ключи валидны)
        """
        errors: list[ValidationErrorDetail] = []

        for key in indicator_keys:
            if not isinstance(key, str) or not key:
                continue

            # Пропускаем базовые OHLCV ключи (open, high, low, close, volume)
            if key in self.OHLCV_KEYS:
                continue

            # Валидируем каждый ключ
            key_errors = self._validate_single_key(key)
            errors.extend(key_errors)

        return errors

    def _validate_single_key(self, key: str) -> list[ValidationErrorDetail]:
        """
        Валидирует один ключ индикатора.

        Args:
            key: Полный ключ индикатора (например, "sma_timeperiod_14_value")

        Returns:
            Список ошибок валидации для этого ключа
        """
        errors: list[ValidationErrorDetail] = []

        # Парсим ключ
        parsed = self._parse_indicator_key(key)
        if not parsed:
            errors.append(
                ValidationErrorDetail(
                    loc=["definition"],
                    msg=f"Неверный формат ключа индикатора: '{key}'",
                    type="invalid_indicator_key_format",
                )
            )
            return errors

        indicator_name = parsed["name"]
        params = parsed["params"]
        output_key = parsed.get("output_key")

        # Проверяем что индикатор существует
        schema = self.schema_loader.get_schema(indicator_name)
        if not schema:
            errors.append(
                ValidationErrorDetail(
                    loc=["definition"],
                    msg=f"Неизвестный индикатор: '{indicator_name}' в ключе '{key}'",
                    type="unknown_indicator",
                )
            )
            return errors

        # Проверяем что output_key корректный (если есть)
        if output_key:
            valid_outputs = schema.get_output_keys()
            if output_key not in valid_outputs:
                errors.append(
                    ValidationErrorDetail(
                        loc=["definition"],
                        msg=f"Неизвестный выходной ключ '{output_key}' для индикатора '{indicator_name}'. Доступные: {', '.join(valid_outputs)}",
                        type="invalid_output_key",
                    )
                )

        # Валидируем типы и значения параметров
        param_errors = self._validate_parameters(key, params, schema)
        errors.extend(param_errors)

        return errors

    def _validate_parameters(
        self, original_key: str, params: dict[str, Any], schema: Any
    ) -> list[ValidationErrorDetail]:
        """
        Валидирует параметры индикатора.

        Args:
            original_key: Оригинальный ключ для сообщений об ошибках
            params: Словарь параметров из распарсенного ключа
            schema: Схема индикатора

        Returns:
            Список ошибок валидации параметров
        """
        errors: list[ValidationErrorDetail] = []

        for param_name, param_value in params.items():
            # Получаем ожидаемый тип параметра из схемы
            expected_type = schema.get_parameter_type(param_name)
            if not expected_type:
                # Параметр не найден в схеме
                errors.append(
                    ValidationErrorDetail(
                        loc=["definition"],
                        msg=f"Неизвестный параметр '{param_name}' в ключе индикатора '{original_key}'",
                        type="unknown_parameter",
                    )
                )
                continue

            # Проверяем что integer параметры действительно целые числа
            if expected_type == "integer":
                if isinstance(param_value, float):
                    # Проверяем что это НЕ целое число (например, 10.1)
                    # 10.0 эквивалентно 10, поэтому это OK
                    if param_value != int(param_value):
                        errors.append(
                            ValidationErrorDetail(
                                loc=["definition"],
                                msg=f"Параметр '{param_name}' должен быть целым числом, получено: {param_value}",
                                type="invalid_parameter_type",
                            )
                        )

            # Проверяем диапазон значений
            param_range = schema.get_parameter_range(param_name)
            if param_range:
                minimum, maximum = param_range
                if minimum is not None and param_value < minimum:
                    errors.append(
                        ValidationErrorDetail(
                            loc=["definition"],
                            msg=f"Значение параметра '{param_name}' ({param_value}) меньше минимального ({minimum}) в ключе '{original_key}'",
                            type="parameter_out_of_range",
                        )
                    )
                if maximum is not None and param_value > maximum:
                    errors.append(
                        ValidationErrorDetail(
                            loc=["definition"],
                            msg=f"Значение параметра '{param_name}' ({param_value}) больше максимального ({maximum}) в ключе '{original_key}'",
                            type="parameter_out_of_range",
                        )
                    )

        return errors

    def _parse_indicator_key(self, key: str) -> dict[str, Any] | None:
        """
        Парсит ключ индикатора и извлекает имя, параметры и output_key.

        Args:
            key: Полный ключ индикатора (например, "sma_timeperiod_14_value")

        Returns:
            Словарь с ключами:
                - name: Имя индикатора
                - params: Словарь параметров
                - output_key: Ключ выходного значения (опционально)
            Или None если не удалось распарсить
        """
        parts = key.split("_")

        if len(parts) < 1:
            return None

        # Удаляем суффикс значения если есть
        output_key = None
        if len(parts) > 1 and parts[-1] in self.VALUE_SUFFIXES:
            output_key = parts[-1]
            parts = parts[:-1]

        if len(parts) < 1:
            return None

        # Первая часть - имя индикатора
        indicator_name = parts[0]

        # Парсим параметры
        params = {}
        i = 1
        while i < len(parts):
            param_name = parts[i]
            if i + 1 < len(parts):
                param_value_str = parts[i + 1]

                # Пытаемся преобразовать в число
                try:
                    if "." in param_value_str:
                        params[param_name] = float(param_value_str)
                    else:
                        params[param_name] = int(param_value_str)
                    i += 2
                except ValueError:
                    # Не удалось преобразовать - возможно это не параметр
                    break
            else:
                break

        return {
            "name": indicator_name,
            "params": params,
            "output_key": output_key,
        }
