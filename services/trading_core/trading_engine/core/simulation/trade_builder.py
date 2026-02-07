"""
Trade Builder - построитель объектов BacktestTrade с расчетами.

Инкапсулирует всю логику расчетов для создания сделки:
- Размер позиции и количество лотов
- Валовая и чистая прибыль
- Комиссии
- Продолжительность сделки
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

import numpy as np
import pandas as pd
from tradeforge_logger import get_logger

from core.common import PositionType
from models.backtest import BacktestConfig, BacktestTrade

logger = get_logger(__name__)


class PositionSize(NamedTuple):
    """
    Результат расчета размера позиции.

    Attributes:
        num_lots: Количество лотов (0 если недостаточно капитала).
        quantity: Общее количество единиц инструмента.
        position_cost: Стоимость позиции в рублях.
    """

    num_lots: int
    quantity: int
    position_cost: float


class TradeBuilder:
    """
    Builder для создания объектов BacktestTrade с финансовыми расчетами.

    Разделяет ответственность между симуляцией бэктеста (executor)
    и построением объектов сделок (builder).

    Attributes:
        config: Конфигурация бэктеста.
        lot_size: Размер лота инструмента.
        df: DataFrame с данными свечей (для расчета duration_candles).
        correlation_id: ID корреляции для логирования.
    """

    def __init__(
        self,
        config: BacktestConfig,
        lot_size: int,
        df: pd.DataFrame,
        correlation_id: str | None = None,
    ):
        """
        Инициализирует TradeBuilder.

        Args:
            config: Конфигурация бэктеста.
            lot_size: Размер лота инструмента.
            df: DataFrame с данными свечей.
            correlation_id: ID корреляции для трейсинга.
        """
        self.config = config
        self.lot_size = lot_size
        self.df = df
        self.correlation_id = correlation_id

    def calculate_position_size(
        self, current_capital: float, entry_price: float
    ) -> PositionSize:
        """
        Рассчитывает размер позиции на основе капитала.

        Args:
            current_capital: Доступный капитал на момент входа.
            entry_price: Цена входа в позицию.

        Returns:
            PositionSize с полями:
                - num_lots: Количество лотов (0 если недостаточно капитала)
                - quantity: Общее количество единиц инструмента
                - position_cost: Стоимость позиции

        Raises:
            ValueError: При невалидных входных данных (capital <= 0, price <= 0).
        """
        # Валидация входных параметров
        if current_capital <= 0:
            raise ValueError(
                f"Invalid current_capital: {current_capital}. "
                "Capital must be positive."
            )

        if entry_price <= 0:
            raise ValueError(
                f"Invalid entry_price: {entry_price}. "
                "Price must be positive."
            )

        # Расчет максимального объема для торговли
        trade_volume = current_capital * self.config.position_size_multiplier
        position_cost_per_lot = entry_price * self.lot_size

        # Проверка достаточности капитала на минимум 1 лот
        if trade_volume < position_cost_per_lot:
            logger.warning(
                "trade_builder.insufficient_capital_for_lot",
                current_capital=current_capital,
                position_cost_per_lot=position_cost_per_lot,
                trade_volume=trade_volume,
                lot_size=self.lot_size,
                correlation_id=self.correlation_id,
            )
            # Возвращаем нулевую позицию - невозможно открыть даже 1 лот
            return PositionSize(num_lots=0, quantity=0, position_cost=0.0)

        # Расчет количества лотов
        max_lots = int(trade_volume / position_cost_per_lot)
        num_lots = max(1, max_lots)
        quantity = num_lots * self.lot_size
        position_cost = entry_price * quantity

        return PositionSize(
            num_lots=num_lots, quantity=quantity, position_cost=position_cost
        )

    def calculate_profit(
        self,
        position: PositionType,
        entry_price: float,
        exit_price: float,
        quantity: int,
        position_cost: float,
    ) -> tuple[float, float, float]:
        """
        Рассчитывает валовую и чистую прибыль с учетом комиссии.

        Args:
            position: Тип позиции (BUY/SELL).
            entry_price: Цена входа.
            exit_price: Цена выхода.
            quantity: Количество единиц инструмента.
            position_cost: Стоимость позиции.

        Returns:
            Tuple (gross_profit_abs, commission_cost, net_profit_abs):
                - gross_profit_abs: Валовая прибыль (без комиссии)
                - commission_cost: Стоимость комиссии
                - net_profit_abs: Чистая прибыль (с комиссией)
        """
        # Валовая прибыль (без комиссии)
        if position == PositionType.BUY:
            price_diff = exit_price - entry_price
        else:  # SELL
            price_diff = entry_price - exit_price
        gross_profit_abs = price_diff * quantity

        # Комиссия (вход + выход)
        turnover = position_cost * 2
        commission_cost = turnover * self.config.commission_rate

        # Чистая прибыль (с комиссией)
        net_profit_abs = gross_profit_abs - commission_cost

        return gross_profit_abs, commission_cost, net_profit_abs

    def calculate_duration(
        self, entry_time: datetime, exit_time: datetime
    ) -> tuple[float, int]:
        """
        Рассчитывает продолжительность сделки.

        Args:
            entry_time: Время входа в позицию.
            exit_time: Время выхода из позиции.

        Returns:
            Tuple (duration_hours, duration_candles):
                - duration_hours: Продолжительность в часах
                - duration_candles: Количество свечей
        """
        duration_timedelta = exit_time - entry_time
        duration_hours = duration_timedelta.total_seconds() / 3600.0

        # Определяем количество свечей
        try:
            entry_idx = self.df.index.get_loc(entry_time)
            exit_idx = self.df.index.get_loc(exit_time)
            duration_candles = abs(exit_idx - entry_idx)
        except KeyError:
            # Если точное время не найдено, возвращаем 0
            duration_candles = 0

        return duration_hours, duration_candles

    def build_trade(
        self,
        position: PositionType,
        entry_time: datetime,
        entry_price: float,
        exit_time: datetime,
        exit_price: float,
        current_capital: float,
        initial_stop_loss: float,
        final_stop_loss: float,
        take_profit: float,
        exit_reason: str,
    ) -> BacktestTrade:
        """
        Создает объект BacktestTrade с полными расчетами.

        Args:
            position: Тип позиции (BUY/SELL).
            entry_time: Время входа в позицию.
            entry_price: Цена входа в позицию.
            exit_time: Время выхода из позиции.
            exit_price: Цена выхода из позиции.
            current_capital: Капитал на момент входа.
            initial_stop_loss: Начальный стоп-лосс.
            final_stop_loss: Финальный стоп-лосс (с учетом трейлинга).
            take_profit: Take profit уровень.
            exit_reason: Причина закрытия сделки.

        Returns:
            Полностью заполненный объект BacktestTrade.

        Raises:
            ValueError: При невалидных входных данных (отрицательные цены,
                неправильный порядок времени, и т.д.).
        """
        # === ВАЛИДАЦИЯ ВХОДНЫХ ДАННЫХ ===
        if entry_price <= 0:
            raise ValueError(
                f"Entry price must be positive, got: {entry_price}. "
                f"Position: {position}, Entry time: {entry_time}"
            )

        if exit_price <= 0:
            raise ValueError(
                f"Exit price must be positive, got: {exit_price}. "
                f"Position: {position}, Exit time: {exit_time}"
            )

        if current_capital < 0:
            raise ValueError(
                f"Capital cannot be negative, got: {current_capital}"
            )

        # Проверка stop loss (если указан)
        if initial_stop_loss is not None and not np.isnan(initial_stop_loss):
            if (
                position == PositionType.BUY
                and initial_stop_loss >= entry_price
            ):
                logger.warning(
                    "trade_builder.invalid_long_stop_loss",
                    entry_price=entry_price,
                    stop_loss=initial_stop_loss,
                    message="Long SL should be below entry price",
                    correlation_id=self.correlation_id,
                )
            elif (
                position == PositionType.SELL
                and initial_stop_loss <= entry_price
            ):
                logger.warning(
                    "trade_builder.invalid_short_stop_loss",
                    entry_price=entry_price,
                    stop_loss=initial_stop_loss,
                    message="Short SL should be above entry price",
                    correlation_id=self.correlation_id,
                )

        # 1. Размер позиции
        pos_size = self.calculate_position_size(current_capital, entry_price)

        # 2. Прибыль и комиссия
        gross_profit_abs, commission_cost, net_profit_abs = (
            self.calculate_profit(
                position,
                entry_price,
                exit_price,
                pos_size.quantity,
                pos_size.position_cost,
            )
        )

        # 3. Капитал после сделки
        exit_capital = current_capital + net_profit_abs

        # 4. Продолжительность
        duration_hours, duration_candles = self.calculate_duration(
            entry_time, exit_time
        )

        # 5. Флаг FLIP
        is_flip = "(FLIP)" in exit_reason

        # 6. Создание объекта
        trade = BacktestTrade(
            # Базовая информация
            position=position.value,
            entry_time=entry_time,
            entry_price=entry_price,
            exit_time=exit_time,
            exit_price=exit_price,
            exit_reason=exit_reason,
            is_flip=is_flip,
            # Размер позиции
            quantity=pos_size.quantity,
            lot_size=self.lot_size,
            num_lots=pos_size.num_lots,
            position_cost=pos_size.position_cost,
            # Капитал
            entry_capital=current_capital,
            exit_capital=exit_capital,
            position_size_pct=self.config.position_size_multiplier * 100.0,
            # Стоп-лосс и тейк-профит
            initial_stop_loss=initial_stop_loss,
            final_stop_loss=final_stop_loss,
            take_profit=take_profit if not np.isnan(take_profit) else None,
            # Финансовые результаты
            gross_profit_abs=gross_profit_abs,
            commission_cost=commission_cost,
            net_profit_abs=net_profit_abs,
            # Статистика
            duration_hours=duration_hours,
            duration_candles=duration_candles,
        )

        logger.debug(
            "trade_builder.trade_created",
            position=trade.position,
            entry_price=float(entry_price),
            exit_price=float(exit_price),
            gross_profit=float(gross_profit_abs),
            commission=float(commission_cost),
            net_profit=float(net_profit_abs),
            net_profit_pct=float(trade.net_profit_pct_on_capital),
            duration_hours=float(duration_hours),
            correlation_id=self.correlation_id,
        )

        return trade
