"""
Pydantic модели для валидации индикаторов Trade Forge.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class IndicatorCategory(str, Enum):
    """Категории индикаторов."""

    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    OSCILLATOR = "oscillator"
    SUPPORT_RESISTANCE = "support_resistance"


class IndicatorComplexity(str, Enum):
    """Уровни сложности индикаторов."""

    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ChartType(str, Enum):
    """Типы отображения на графике."""

    LINE = "line"
    AREA = "area"
    HISTOGRAM = "histogram"
    OVERLAY = "overlay"


class ParameterSchema(BaseModel):
    """Схема параметра индикатора."""

    type: str = Field(..., description="Тип параметра")
    minimum: Optional[Union[int, float]] = Field(
        None, description="Минимальное значение"
    )
    maximum: Optional[Union[int, float]] = Field(
        None, description="Максимальное значение"
    )
    default: Optional[Union[int, float, bool, str]] = Field(
        None, description="Значение по умолчанию"
    )
    description: Optional[str] = Field(None, description="Описание параметра")
    enum: Optional[List[Union[str, int, float]]] = Field(
        None, description="Список допустимых значений"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed_types = ["integer", "number", "boolean", "string"]
        if v not in allowed_types:
            raise ValueError(
                f"Тип должен быть одним из: {', '.join(allowed_types)}"
            )
        return v


class OutputSchema(BaseModel):
    """Схема выходного значения индикатора."""

    type: str = Field(..., description="Тип выходного значения")
    description: str = Field(..., description="Описание выходного значения")
    range: Optional[Dict[str, Union[int, float]]] = Field(
        None, description="Диапазон значений"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed_types = ["number", "boolean", "integer"]
        if v not in allowed_types:
            raise ValueError(
                f"Тип должен быть одним из: {', '.join(allowed_types)}"
            )
        return v


class ParametersSchemaDefinition(BaseModel):
    """Схема параметров индикатора."""

    type: str = Field("object", description="Тип схемы")
    required: Optional[List[str]] = Field(
        None, description="Обязательные параметры"
    )
    properties: Dict[str, ParameterSchema] = Field(
        ..., description="Свойства параметров"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "object":
            raise ValueError("Тип схемы параметров должен быть 'object'")
        return v


class OutputSchemaDefinition(BaseModel):
    """Схема выходных значений индикатора."""

    type: str = Field("object", description="Тип схемы")
    properties: Dict[str, OutputSchema] = Field(
        ..., description="Свойства выходных значений"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "object":
            raise ValueError(
                "Тип схемы выходных значений должен быть 'object'"
            )
        return v


class ParameterGroup(BaseModel):
    """Группа параметров для UI."""

    name: str = Field(..., description="Название группы")
    parameters: List[str] = Field(
        ..., description="Список параметров в группе"
    )


class FrontendConfig(BaseModel):
    """Конфигурация для фронтенда."""

    icon: Optional[str] = Field(None, description="Иконка индикатора")
    color: Optional[str] = Field(
        None, description="Цвет по умолчанию", pattern=r"^#[0-9A-Fa-f]{6}$"
    )
    chart_type: Optional[ChartType] = Field(
        None, description="Тип отображения на графике"
    )
    parameter_groups: Optional[List[ParameterGroup]] = Field(
        None, description="Группировка параметров в UI"
    )


class SystemIndicatorDefinition(BaseModel):
    """Определение системного индикатора."""

    name: str = Field(
        ...,
        description="Уникальное имя семейства индикаторов",
        pattern=r"^[a-z][a-z0-9_]*$",
        max_length=50,
    )
    display_name: str = Field(
        ..., description="Человекочитаемое название", max_length=100
    )
    description: Optional[str] = Field(None, description="Описание индикатора")
    category: IndicatorCategory = Field(
        ..., description="Категория индикатора"
    )
    complexity: IndicatorComplexity = Field(
        ..., description="Уровень сложности"
    )
    parameters_schema: ParametersSchemaDefinition = Field(
        ..., description="Схема параметров"
    )
    output_schema: OutputSchemaDefinition = Field(
        ..., description="Схема выходных значений"
    )
    key_template: str = Field(
        ..., description="Шаблон для генерации ключа", max_length=200
    )
    is_enabled: bool = Field(True, description="Доступен ли индикатор")
    frontend_config: Optional[FrontendConfig] = Field(
        None, description="Конфигурация для фронтенда"
    )

    @model_validator(mode="after")
    def validate_key_template(self) -> SystemIndicatorDefinition:
        """Валидация шаблона ключа."""
        template = self.key_template

        # Проверяем, что в шаблоне есть {name}
        if "{name}" not in template:
            raise ValueError("Шаблон ключа должен содержать {name}")

        # Проверяем, что все параметры из required присутствуют в шаблоне
        if self.parameters_schema.required:
            for param in self.parameters_schema.required:
                param_placeholder = f"{{{param}}}"
                if param_placeholder not in template:
                    raise ValueError(
                        f"Шаблон ключа должен содержать плейсхолдер для обязательного параметра: {param_placeholder}"
                    )

        return self

    @model_validator(mode="after")
    def validate_parameter_groups(self) -> SystemIndicatorDefinition:
        """Валидация групп параметров."""
        if self.frontend_config and self.frontend_config.parameter_groups:
            all_params = set(self.parameters_schema.properties.keys())
            grouped_params = set()

            for group in self.frontend_config.parameter_groups:
                for param in group.parameters:
                    if param not in all_params:
                        raise ValueError(
                            f"Параметр '{param}' в группе '{group.name}' не существует в схеме параметров"
                        )
                    grouped_params.add(param)

            # Предупреждаем, если есть негруппированные параметры
            ungrouped = all_params - grouped_params
            if ungrouped:
                # В MVP можно просто логировать предупреждение
                pass

        return self


class SystemIndicatorsList(BaseModel):
    """Список системных индикаторов."""

    indicators: List[SystemIndicatorDefinition] = Field(
        ..., description="Список индикаторов"
    )

    @field_validator("indicators")
    @classmethod
    def validate_unique_names(
        cls, indicators: List[SystemIndicatorDefinition]
    ) -> List[SystemIndicatorDefinition]:
        """Проверяем уникальность имен индикаторов."""
        names = [indicator.name for indicator in indicators]
        if len(names) != len(set(names)):
            raise ValueError("Имена индикаторов должны быть уникальными")
        return indicators


class IndicatorKeyGenerator:
    """Утилита для генерации ключей индикаторов."""

    @staticmethod
    def generate_key(template: str, name: str, params: Dict[str, Any]) -> str:
        """
        Генерирует ключ индикатора на основе шаблона и параметров.

        Args:
            template: Шаблон ключа с плейсхолдерами
            name: Имя индикатора
            params: Словарь параметров

        Returns:
            Сгенерированный ключ индикатора
        """
        format_dict = {"name": name}
        format_dict.update(params)

        try:
            return template.format(**format_dict)
        except KeyError as e:
            raise ValueError(f"Отсутствует параметр для шаблона: {e}")

    @staticmethod
    def generate_keys_for_outputs(
        template: str, name: str, params: Dict[str, Any], outputs: List[str]
    ) -> List[str]:
        """
        Генерирует ключи для всех выходных значений индикатора.

        Args:
            template: Шаблон ключа
            name: Имя индикатора
            params: Параметры индикатора
            outputs: Список выходных значений

        Returns:
            Список сгенерированных ключей
        """
        keys = []
        for output_key in outputs:
            format_dict = {"name": name, "output_key": output_key}
            format_dict.update(params)

            try:
                key = template.format(**format_dict)
                keys.append(key)
            except KeyError as e:
                raise ValueError(f"Отсутствует параметр для шаблона: {e}")

        return keys


class IndicatorValidationError(Exception):
    """Исключение для ошибок валидации индикаторов."""


class IndicatorValidator:
    """Валидатор индикаторов."""

    @staticmethod
    def validate_json_against_schema(
        data: Dict[str, Any]
    ) -> SystemIndicatorDefinition:
        """
        Валидирует JSON-данные индикатора против схемы.

        Args:
            data: JSON-данные индикатора

        Returns:
            Валидированный объект индикатора

        Raises:
            IndicatorValidationError: При ошибках валидации
        """
        try:
            return SystemIndicatorDefinition.model_validate(data)
        except Exception as e:
            raise IndicatorValidationError(f"Ошибка валидации индикатора: {e}")

    @staticmethod
    def validate_indicators_list(
        data: List[Dict[str, Any]]
    ) -> SystemIndicatorsList:
        """
        Валидирует список индикаторов.

        Args:
            data: Список JSON-данных индикаторов

        Returns:
            Валидированный список индикаторов

        Raises:
            IndicatorValidationError: При ошибках валидации
        """
        try:
            return SystemIndicatorsList.model_validate({"indicators": data})
        except Exception as e:
            raise IndicatorValidationError(
                f"Ошибка валидации списка индикаторов: {e}"
            )
