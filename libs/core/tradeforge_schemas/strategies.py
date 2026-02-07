"""
Унифицированные Pydantic схемы для работы со стратегиями.

Содержит все схемы для создания, валидации, обновления стратегий.
Использует AST-подход из Internal API как источник истины.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .base import ValidationErrorDetail

# === AST УЗЛЫ ОПРЕДЕЛЕНИЯ СТРАТЕГИИ ===


# --- Узлы-значения ---
class ValueNode(BaseModel):
    """Узел со значением константы."""

    type: Literal["VALUE"] = "VALUE"
    value: float


class IndicatorValueNode(BaseModel):
    """Узел со значением индикатора."""

    type: Literal["INDICATOR_VALUE"]
    key: str = Field(
        ...,
        description="Полный ключ индикатора (например, 'ema_timeperiod_12_value')",
    )


class PrevIndicatorValueNode(BaseModel):
    """Узел со значением индикатора с предыдущей свечи."""

    type: Literal["PREV_INDICATOR_VALUE"]
    key: str = Field(..., description="Полный ключ индикатора")


ResolvableValue = Annotated[
    Union[ValueNode, IndicatorValueNode, PrevIndicatorValueNode],
    Field(discriminator="type"),
]


# --- Узлы-условия ---
class ComparisonNode(BaseModel):
    """Узел сравнения двух значений."""

    type: Literal["GREATER_THAN", "LESS_THAN", "EQUALS"]
    left: ResolvableValue
    right: ResolvableValue


class CrossoverNode(BaseModel):
    """Узел пересечения двух линий индикаторов."""

    type: Literal["CROSSOVER_UP", "CROSSOVER_DOWN"]
    line1: ResolvableValue
    line2: ResolvableValue


class SpecialExitNode(BaseModel):
    """Специальный узел для флипа SuperTrend."""

    type: Literal["SUPER_TREND_FLIP"]
    indicator_key: str = Field(..., description="Ключ SuperTrend индикатора")
    target_direction: Literal["OPPOSITE_TO_POSITION"]


# Универсальный тип для всех возможных условий
AnyConditionNode = Annotated[
    Union[ComparisonNode, CrossoverNode, SpecialExitNode, "LogicalNode"],
    Field(discriminator="type"),
]


class LogicalNode(BaseModel):
    """Логический узел AND/OR с вложенными условиями."""

    type: Literal["AND", "OR"]
    conditions: Annotated[
        list[AnyConditionNode],
        Field(min_length=1),
    ]


# Типы для входных условий (без SpecialExitNode)
AnyEntryConditionNode = Annotated[
    Union[ComparisonNode, CrossoverNode, LogicalNode],
    Field(discriminator="type"),
]

# Типы для выходных условий (включая SpecialExitNode)
AnyExitConditionNode = Annotated[
    Union[ComparisonNode, CrossoverNode, LogicalNode, SpecialExitNode],
    Field(discriminator="type"),
]


# --- Узлы для Stop Loss ---
class IndicatorBasedStopLossNode(BaseModel):
    """Stop Loss на основе индикатора."""

    type: Literal["INDICATOR_BASED"]
    buy_value_key: str | None = Field(
        None, description="Ключ значения для long позиций"
    )
    sell_value_key: str | None = Field(
        None, description="Ключ значения для short позиций"
    )


class PercentageStopLossNode(BaseModel):
    """Stop Loss в процентах от цены входа."""

    type: Literal["PERCENTAGE"]
    percentage: float = Field(
        ..., description="Процент стоп-лосса", gt=0, le=100
    )


AnyStopLossNode = Annotated[
    Union[IndicatorBasedStopLossNode, PercentageStopLossNode],
    Field(discriminator="type"),
]


# === ОСНОВНАЯ СХЕМА ОПРЕДЕЛЕНИЯ СТРАТЕГИИ ===


class StrategyDefinition(BaseModel):
    """
    Полное определение торговой стратегии в формате AST.

    Единая схема, используемая во всех сервисах Trade Forge.
    """

    entry_buy_conditions: AnyEntryConditionNode | None = Field(
        None, description="Условия входа в long позицию"
    )
    entry_sell_conditions: AnyEntryConditionNode | None = Field(
        None, description="Условия входа в short позицию"
    )
    exit_conditions: AnyExitConditionNode | None = Field(
        None, description="Условия выхода из позиции"
    )
    stop_loss: AnyStopLossNode | None = Field(
        None, description="Настройки stop loss"
    )
    take_profit: dict | None = Field(
        None, description="Настройки take profit (будет детализирован позже)"
    )


# === API СХЕМЫ ===


class StrategyBase(BaseModel):
    """Базовая схема стратегии с общими полями."""

    name: str = Field(
        ..., min_length=3, max_length=100, description="Название стратегии"
    )
    description: str | None = Field(None, description="Описание стратегии")
    definition: StrategyDefinition = Field(
        ..., description="Определение стратегии (AST)"
    )


class StrategyCreateRequest(StrategyBase):
    """Запрос на создание новой стратегии."""

    pass


class StrategyUpdateRequest(BaseModel):
    """Запрос на обновление существующей стратегии."""

    name: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        description="Новое название стратегии",
    )
    description: str | None = Field(
        None, description="Новое описание стратегии"
    )
    definition: StrategyDefinition | None = Field(
        None, description="Новое определение стратегии"
    )


class StrategyResponse(StrategyBase):
    """Полная информация о стратегии."""

    id: uuid.UUID = Field(..., description="ID стратегии")
    user_id: uuid.UUID = Field(..., description="ID владельца")
    created_at: datetime = Field(..., description="Время создания")
    updated_at: datetime = Field(
        ..., description="Время последнего обновления"
    )
    is_deleted: bool = Field(False, description="Флаг мягкого удаления")

    model_config = ConfigDict(from_attributes=True)


class LastBacktestInfo(BaseModel):
    """Информация о последнем бэктесте стратегии."""

    id: uuid.UUID
    ticker: str
    created_at: datetime
    status: str
    net_total_profit_pct: str | None = None


class StrategySummary(BaseModel):
    """Краткая информация о стратегии для списков (без definition)."""

    id: uuid.UUID = Field(..., description="ID стратегии")
    user_id: uuid.UUID = Field(..., description="ID владельца")
    name: str = Field(..., description="Название стратегии")
    description: str | None = Field(None, description="Описание стратегии")
    created_at: datetime = Field(..., description="Время создания")
    updated_at: datetime = Field(
        ..., description="Время последнего обновления"
    )
    is_deleted: bool = Field(False, description="Флаг мягкого удаления")
    backtests_count: int = Field(
        ..., description="Количество выполненных бэктестов"
    )
    last_backtest: LastBacktestInfo | None = Field(
        None, description="Информация о последнем бэктесте"
    )

    model_config = ConfigDict(from_attributes=True)


# === СХЕМЫ ВАЛИДАЦИИ ===


class StrategyValidationRequest(BaseModel):
    """Запрос на валидацию определения стратегии."""

    definition: StrategyDefinition = Field(
        ..., description="Определение стратегии для валидации"
    )
    name: str | None = Field(
        None,
        min_length=1,
        max_length=255,
        description="Название для проверки уникальности",
    )
    strategy_id: uuid.UUID | None = Field(
        None,
        description="ID редактируемой стратегии (исключается из проверки уникальности)",
    )


class RequiredIndicator(BaseModel):
    """Информация о необходимом индикаторе."""

    name: str = Field(..., description="Название индикатора")
    params: dict = Field(..., description="Параметры индикатора")
    indicator_key: str = Field(..., description="Уникальный ключ индикатора")


class StrategySortBy(str, enum.Enum):
    """Доступные поля для сортировки стратегий."""

    NAME = "name"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    BACKTESTS_COUNT = "backtests_count"


class StrategyValidationResponse(BaseModel):
    """
    Результат валидации стратегии в формате RFC 7807.

    Может содержать как успешный результат, так и детали ошибок.
    """

    is_valid: bool = Field(..., description="Является ли стратегия валидной")
    required_indicators: list[str] = Field(
        default_factory=list,
        description="Список необходимых базовых ключей индикаторов",
    )

    # Поля для ошибок (RFC 7807 формат) - только если есть ошибки
    type: str | None = Field(None, description="URI типа ошибки")
    title: str | None = Field(None, description="Краткое описание ошибки")
    status: int | None = Field(None, description="HTTP статус код")
    detail: str | None = Field(None, description="Детальное описание ошибки")
    instance: str | None = Field(None, description="URI экземпляра проблемы")
    errors: list[ValidationErrorDetail] | None = Field(
        None, description="Список детальных ошибок валидации"
    )
