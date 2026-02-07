from __future__ import annotations

import warnings
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator


class BacktestTrade(BaseModel):
    """
    Расширенная модель для одной симулированной сделки с полной информацией.
    Содержит все данные для детального анализа торговой истории.
    """

    # === БАЗОВАЯ ИНФОРМАЦИЯ О СДЕЛКЕ ===
    position: Literal["BUY", "SELL"] = Field(
        description="Тип позиции: покупка (BUY) или продажа (SELL)"
    )
    entry_time: datetime = Field(description="Время входа в позицию")
    entry_price: float = Field(description="Цена входа в позицию")
    exit_time: datetime = Field(description="Время выхода из позиции")
    exit_price: float = Field(description="Цена выхода из позиции")
    exit_reason: str = Field(description="Причина закрытия сделки")
    is_flip: bool = Field(
        default=False, description="Флаг разворота позиции (флип)"
    )

    # === ИНФОРМАЦИЯ О РАЗМЕРЕ ПОЗИЦИИ ===
    quantity: int = Field(
        description="Общее количество акций в сделке (num_lots × lot_size)"
    )
    lot_size: int = Field(description="Размер лота инструмента")
    num_lots: int = Field(description="Количество купленных/проданных лотов")
    position_cost: float = Field(
        description="Полная стоимость позиции (entry_price × quantity)"
    )

    # === ИНФОРМАЦИЯ О КАПИТАЛЕ ===
    entry_capital: float = Field(
        description="Капитал на момент входа в сделку"
    )
    exit_capital: float = Field(
        description="Капитал после закрытия сделки (entry_capital + net_profit_abs)"
    )
    position_size_pct: float = Field(
        description="Процент использованного капитала (плечо), например 300.0 для 3x"
    )

    # === СТОП-ЛОСС И ТЕЙК-ПРОФИТ ===
    initial_stop_loss: float | None = Field(
        description="Начальный стоп-лосс при входе в позицию"
    )
    final_stop_loss: float | None = Field(
        description="Финальный стоп-лосс при выходе (может отличаться при трейлинге)"
    )
    take_profit: float | None = Field(
        default=None, description="Уровень тейк-профита (если используется)"
    )

    # === ФИНАНСОВЫЕ РЕЗУЛЬТАТЫ (GROSS - БЕЗ КОМИССИИ) ===
    gross_profit_abs: float = Field(
        description="Валовая прибыль в рублях (без учета комиссии)"
    )
    commission_cost: float = Field(
        description="Сумма комиссии за сделку в рублях"
    )

    # === ФИНАНСОВЫЕ РЕЗУЛЬТАТЫ (NET - С КОМИССИЕЙ) ===
    net_profit_abs: float = Field(
        description="Чистая прибыль в рублях (с учетом комиссии)"
    )

    # === СТАТИСТИКА СДЕЛКИ ===
    duration_hours: float = Field(
        description="Продолжительность сделки в часах"
    )
    duration_candles: int = Field(description="Количество свечей в сделке")

    # === COMPUTED FIELDS ===

    @computed_field
    @property
    def gross_profit_pct_on_position(self) -> float:
        """
        Валовая процентная прибыль относительно стоимости позиции.
        Показывает эффективность сделки без учета комиссии.
        """
        if self.position_cost == 0:
            return 0.0
        return (self.gross_profit_abs / self.position_cost) * 100.0

    @computed_field
    @property
    def gross_profit_pct_on_capital(self) -> float:
        """
        Валовая процентная прибыль относительно капитала.
        Показывает реальное влияние сделки на баланс без учета комиссии.
        """
        if self.entry_capital == 0:
            return 0.0
        return (self.gross_profit_abs / self.entry_capital) * 100.0

    @computed_field
    @property
    def net_profit_pct_on_position(self) -> float:
        """
        Чистая процентная прибыль относительно стоимости позиции.
        Показывает эффективность сделки с учетом комиссии.
        """
        if self.position_cost == 0:
            return 0.0
        return (self.net_profit_abs / self.position_cost) * 100.0

    @computed_field
    @property
    def net_profit_pct_on_capital(self) -> float:
        """
        Чистая процентная прибыль относительно капитала.
        Показывает реальное влияние сделки на баланс с учетом комиссии.
        ОСНОВНАЯ МЕТРИКА для пользователя.
        """
        if self.entry_capital == 0:
            return 0.0
        return (self.net_profit_abs / self.entry_capital) * 100.0

    @computed_field
    @property
    def capital_change_pct(self) -> float:
        """
        Процентное изменение капитала после сделки.
        Альтернативный способ расчета: (exit_capital - entry_capital) / entry_capital * 100
        """
        if self.entry_capital == 0:
            return 0.0
        return (
            (self.exit_capital - self.entry_capital) / self.entry_capital
        ) * 100.0

    @computed_field
    @property
    def stop_loss_distance_pct(self) -> float | None:
        """
        Расстояние от входа до начального стоп-лосса в процентах.
        Полезно для анализа риск-менеджмента.
        """
        if self.initial_stop_loss is None or self.entry_price == 0:
            return None

        distance = abs(self.entry_price - self.initial_stop_loss)
        return (distance / self.entry_price) * 100.0

    @computed_field
    @property
    def commission_pct_on_position(self) -> float:
        """
        Процент комиссии относительно стоимости позиции.
        Показывает реальную стоимость сделки.
        """
        if self.position_cost == 0:
            return 0.0
        return (self.commission_cost / self.position_cost) * 100.0

    # === BACKWARD COMPATIBILITY ===
    # Оставляем старые поля как алиасы для обратной совместимости

    @computed_field
    @property
    def profit_abs(self) -> float:
        """DEPRECATED: Используйте gross_profit_abs. Оставлено для обратной совместимости."""
        return self.gross_profit_abs

    @computed_field
    @property
    def profit_pct(self) -> float:
        """DEPRECATED: Используйте net_profit_pct_on_capital. Оставлено для обратной совместимости."""
        return self.net_profit_pct_on_capital

    @computed_field
    @property
    def stop_loss(self) -> float | None:
        """DEPRECATED: Используйте final_stop_loss. Оставлено для обратной совместимости."""
        return self.final_stop_loss

    class Config:
        from_attributes = True


class BacktestConfig(BaseModel):
    """Конфигурация параметров симуляции бэктеста."""

    initial_balance: float = Field(
        default=100000.0,
        gt=0,
        description="Начальный капитал для симуляции",
    )
    commission_rate: float = Field(
        default=0.0003,
        ge=0,
        le=0.01,
        description="Процент комиссии за оборот (0.03% = 0.0003)",
    )
    position_size_multiplier: float = Field(
        default=3.0,
        gt=0,
        le=10.0,
        description="Множитель размера позиции (1.0 = 100%, 3.0 = 300%)",
    )

    @field_validator("initial_balance")
    @classmethod
    def validate_initial_balance(cls, v: float) -> float:
        """
        Валидирует начальный баланс для бэктеста.

        Args:
            v: Значение начального баланса.

        Returns:
            Валидированное значение.

        Raises:
            ValueError: Если баланс слишком маленький или слишком большой.
        """
        if v < 1000:
            raise ValueError(
                f"Минимальный баланс для бэктеста: 1,000₽ (получено: {v:,.0f}₽)"
            )
        if v > 1_000_000_000:
            raise ValueError(
                f"Максимальный баланс: 1 млрд₽ (получено: {v:,.0f}₽)"
            )
        return v

    @field_validator("commission_rate")
    @classmethod
    def validate_commission(cls, v: float) -> float:
        """
        Валидирует процент комиссии и предупреждает если он слишком высокий.

        Args:
            v: Процент комиссии в десятичной форме.

        Returns:
            Валидированное значение.
        """
        if v > 0.01:  # 1%
            warnings.warn(
                f"Комиссия {v*100:.2f}% выше 1% - проверьте настройки. "
                f"Обычная комиссия на MOEX: 0.03-0.05%",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("position_size_multiplier")
    @classmethod
    def validate_position_size(cls, v: float) -> float:
        """
        Валидирует множитель размера позиции и предупреждает о высоких рисках.

        Args:
            v: Множитель размера позиции (плечо).

        Returns:
            Валидированное значение.
        """
        if v > 5.0:
            warnings.warn(
                f"Плечо {v}x очень высокое - высокий риск ликвидации. "
                f"Рекомендуется использовать не более 3x для консервативной торговли.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @classmethod
    def from_simulation_params(cls, params: dict[str, Any]) -> BacktestConfig:
        """
        Создает конфиг из словаря simulation_params.

        Поддерживает обратную совместимость со старым форматом:
        - commission_pct (%) -> commission_rate (decimal)
        - position_size_pct (%) -> position_size_multiplier (decimal)

        Args:
            params: Словарь с параметрами симуляции из БД.

        Returns:
            BacktestConfig: Сконфигурированный экземпляр.

        Examples:
            >>> # Новый формат
            >>> params = {"commission_rate": 0.0004, "position_size_multiplier": 3.0}
            >>> config = BacktestConfig.from_simulation_params(params)

            >>> # Старый формат (обратная совместимость)
            >>> params = {"commission_pct": 0.04, "position_size_pct": 300.0}
            >>> config = BacktestConfig.from_simulation_params(params)
        """
        # === ОБРАТНАЯ СОВМЕСТИМОСТЬ: commission ===
        commission_rate = params.get("commission_rate")
        if commission_rate is None:
            # Старый формат: процент -> десятичная дробь
            commission_pct = params.get(
                "commission_pct", 0.04
            )  # 0.04% default
            commission_rate = commission_pct / 100.0

        # === ОБРАТНАЯ СОВМЕСТИМОСТЬ: position_size ===
        position_size_multiplier = params.get("position_size_multiplier")
        if position_size_multiplier is None:
            # Старый формат: процент -> множитель
            position_size_pct = params.get(
                "position_size_pct", 300.0
            )  # 300% default
            position_size_multiplier = position_size_pct / 100.0

        return cls(
            initial_balance=params.get("initial_balance", 100000.0),
            commission_rate=commission_rate,
            position_size_multiplier=position_size_multiplier,
        )
