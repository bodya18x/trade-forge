from __future__ import annotations

import uuid
import warnings
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from models.ast_nodes import AnyConditionNode

# --- Блоки управления торговлей ---


class StopLossConfig(BaseModel):
    """Конфигурация для расчета Stop Loss."""

    type: Literal["INDICATOR_BASED", "PERCENTAGE", "FIXED_PRICE"]
    # Для INDICATOR_BASED
    buy_value_key: str | None = Field(
        None, description="Ключ индикатора для SL в лонг позиции"
    )
    sell_value_key: str | None = Field(
        None, description="Ключ индикатора для SL в шорт позиции"
    )
    # Для PERCENTAGE
    percentage: float | None = Field(
        None, gt=0, description="Процент от цены входа"
    )

    @field_validator("percentage")
    @classmethod
    def validate_percentage(cls, v: float | None) -> float | None:
        """
        Валидирует процент Stop Loss.

        Args:
            v: Процент в десятичной форме.

        Returns:
            Валидированное значение.

        Raises:
            ValueError: Если процент некорректен.
        """
        if v is not None:
            if v <= 0:
                raise ValueError(
                    f"Процент Stop Loss должен быть положительным (получено: {v})"
                )
            if v > 50:
                raise ValueError(
                    f"Процент Stop Loss не может быть больше 50% (получено: {v}). "
                    f"Это приведет к слишком большим потерям."
                )
            if v > 10:
                warnings.warn(
                    f"Stop Loss {v}% очень широкий. "
                    f"Рекомендуется использовать 1-5% для эффективного управления рисками.",
                    UserWarning,
                    stacklevel=2,
                )
        return v


class TakeProfitConfig(BaseModel):
    """Конфигурация для расчета Take Profit."""

    type: Literal["RISK_REWARD", "PERCENTAGE"]
    # Для RISK_REWARD
    risk_reward_ratio: float | None = Field(
        None, gt=0, description="Соотношение риск/прибыль"
    )
    # Для PERCENTAGE
    percentage: float | None = Field(
        None, gt=0, description="Процент от цены входа"
    )

    @field_validator("percentage")
    @classmethod
    def validate_percentage(cls, v: float | None) -> float | None:
        """
        Валидирует процент Take Profit.

        Args:
            v: Процент в десятичной форме.

        Returns:
            Валидированное значение.

        Raises:
            ValueError: Если процент некорректен.
        """
        if v is not None:
            if v <= 0:
                raise ValueError(
                    f"Процент Take Profit должен быть положительным (получено: {v})"
                )
            if v > 100:
                raise ValueError(
                    f"Процент Take Profit не может быть больше 100% (получено: {v})"
                )
        return v

    @field_validator("risk_reward_ratio")
    @classmethod
    def validate_rr_ratio(cls, v: float | None) -> float | None:
        """
        Валидирует соотношение риск/прибыль.

        Args:
            v: Соотношение риск/прибыль.

        Returns:
            Валидированное значение.

        Raises:
            ValueError: Если соотношение некорректно.
        """
        if v is not None:
            if v <= 0:
                raise ValueError(
                    f"Risk/Reward ratio должен быть положительным (получено: {v})"
                )
            if v < 0.5:
                warnings.warn(
                    f"Risk/Reward ratio {v} очень низкий. "
                    f"Рекомендуется использовать соотношение >= 1.0 для прибыльной торговли. "
                    f"При RR < 1 требуется win rate > 50% для прибыльности.",
                    UserWarning,
                    stacklevel=2,
                )
        return v


# --- Полная модель определения стратегии ---


class StrategyDefinition(BaseModel):
    """
    Полное определение стратегии, как оно хранится в `strategies.definition`.
    Это и есть наш AST.
    """

    entry_buy_conditions: AnyConditionNode | None = None
    entry_sell_conditions: AnyConditionNode | None = None
    exit_long_conditions: AnyConditionNode | None = (
        None  # Условия выхода из Long
    )
    exit_short_conditions: AnyConditionNode | None = (
        None  # Условия выхода из Short
    )
    exit_conditions: AnyConditionNode | None = Field(
        None, description="Условия выхода, если есть. Иначе выход по SL/TP."
    )
    stop_loss: StopLossConfig | None = None
    take_profit: TakeProfitConfig | None = None


class StrategyModel(BaseModel):
    """Модель для представления стратегии из базы данных."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    definition: StrategyDefinition
