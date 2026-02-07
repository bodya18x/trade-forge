from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# --- Базовые элементы ---


class ValueNode(BaseModel):
    """
    Узел, представляющий константное числовое значение.

    Examples:
        >>> node = ValueNode(value=50.0)
        >>> print(node.value)
        50.0
    """

    type: Literal["VALUE"] = "VALUE"
    value: float


class IndicatorValueNode(BaseModel):
    """
    Узел, представляющий ссылку на значение индикатора на ТЕКУЩЕЙ свече.

    Examples:
        >>> node = IndicatorValueNode(key="rsi_timeperiod_14_value")
        >>> print(node.key)
        rsi_timeperiod_14_value
    """

    type: Literal["INDICATOR_VALUE"] = "INDICATOR_VALUE"
    key: str = Field(
        ...,
        description="Уникальный ключ индикатора, например, 'sma_period_20_value'",
    )


class PrevIndicatorValueNode(BaseModel):
    """Узел, представляющий ссылку на значение индикатора на ПРЕДЫДУЩЕЙ свече."""

    type: Literal["PREV_INDICATOR_VALUE"] = "PREV_INDICATOR_VALUE"
    key: str = Field(..., description="Уникальный ключ индикатора")


# Объединение всех типов узлов, которые могут возвращать значение (число)
ResolvableValue = Annotated[
    ValueNode | IndicatorValueNode | PrevIndicatorValueNode,
    Field(discriminator="type"),
]

# --- Узлы-условия (возвращают True/False) ---


class ComparisonNode(BaseModel):
    """
    Узел для операций сравнения (>, <, ==).

    Examples:
        >>> # RSI > 70 (перекупленность)
        >>> node = ComparisonNode(
        ...     type="GREATER_THAN",
        ...     left=IndicatorValueNode(key="rsi_timeperiod_14_value"),
        ...     right=ValueNode(value=70.0)
        ... )
    """

    type: Literal["GREATER_THAN", "LESS_THAN", "EQUALS"]
    left: ResolvableValue
    right: ResolvableValue


class CrossoverNode(BaseModel):
    """
    Узел для проверки пересечения двух линий.

    Examples:
        >>> # EMA(12) пересекает EMA(50) снизу вверх (золотой крест)
        >>> node = CrossoverNode(
        ...     type="CROSSOVER_UP",
        ...     line1=IndicatorValueNode(key="ema_timeperiod_12_value"),
        ...     line2=IndicatorValueNode(key="ema_timeperiod_50_value")
        ... )
    """

    type: Literal["CROSSOVER_UP", "CROSSOVER_DOWN"]
    line1: ResolvableValue = Field(
        ..., description="Линия, которая пересекает"
    )
    line2: ResolvableValue = Field(
        ..., description="Линия, которую пересекают"
    )


class SpecialConditionNode(BaseModel):
    """
    Узел для более сложных, инкапсулированных условий,
    которые требуют знания о состоянии позиции.
    """

    type: Literal["SUPER_TREND_FLIP", "MACD_CROSSOVER_FLIP"]
    indicator_key: str  # Основной ключ индикатора
    # Дополнительные ключи могут понадобиться для MACD
    signal_key: str | None = None
    target_direction: Literal["OPPOSITE_TO_POSITION"]


# Объединение всех типов узлов, которые являются условиями
ConditionNode = Annotated[
    ComparisonNode | CrossoverNode | SpecialConditionNode,
    Field(discriminator="type"),
]

# --- Логические узлы-контейнеры ---


class LogicalNode(BaseModel):
    """Узел для логических операций AND/OR."""

    type: Literal["AND", "OR"]
    conditions: list[AnyConditionNode]  # Используем ForwardRef для рекурсии


# Объединение всех возможных узлов-условий, включая логические
AnyConditionNode = Annotated[
    LogicalNode | ConditionNode, Field(discriminator="type")
]

# Обновляем ссылки для рекурсивной модели
LogicalNode.model_rebuild()
