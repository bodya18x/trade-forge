"""
Exit Checker - проверка условий выхода из позиций.

Отвечает за определение момента закрытия позиции на основе:
- Stop Loss
- Take Profit
- Exit сигналов стратегии
- Флипов (разворотов позиции)
"""

from __future__ import annotations

import numpy as np
from tradeforge_logger import get_logger

from core.common import ExitReason, PositionType
from core.simulation.data_cache import CachedData

logger = get_logger(__name__)


class ExitInfo:
    """
    Информация о выходе из позиции.

    Содержит все необходимые данные для закрытия сделки.

    Attributes:
        reason: Причина выхода (Stop Loss, Take Profit, Exit Signal, etc).
        price: Цена выхода из позиции.
        is_flip: Флаг разворота позиции (переход из Long в Short или наоборот).

    Examples:
        >>> exit_info = ExitInfo(ExitReason.STOP_LOSS, price=95.5, is_flip=False)
        >>> print(exit_info.reason)
        ExitReason.STOP_LOSS
    """

    __slots__ = ("reason", "price", "is_flip")

    def __init__(
        self,
        reason: ExitReason,
        price: float,
        is_flip: bool = False,
    ):
        """
        Инициализирует информацию о выходе.

        Args:
            reason: Причина закрытия позиции.
            price: Цена выхода.
            is_flip: Происходит ли переворот позиции.
        """
        self.reason = reason
        self.price = price
        self.is_flip = is_flip


class TradingState:
    """
    Состояние текущей торговой позиции.

    Инкапсулирует всю информацию о текущей открытой позиции
    для упрощения передачи между методами.

    Attributes:
        position_type: Тип текущей позиции (BUY/SELL) или None если нет позиции.
        entry_price: Цена входа в позицию.
        entry_time: Время входа в позицию.
        entry_capital: Капитал на момент входа.
        initial_stop_loss: Начальный стоп-лосс.
        current_stop_loss: Текущий стоп-лосс (может меняться при trailing).
        current_take_profit: Текущий take profit.
        current_capital: Текущий доступный капитал.
    """

    __slots__ = (
        "position_type",
        "entry_price",
        "entry_time",
        "entry_capital",
        "initial_stop_loss",
        "current_stop_loss",
        "current_take_profit",
        "current_capital",
    )

    def __init__(self, current_capital: float = 0.0):
        """
        Инициализирует состояние торговли.

        Args:
            current_capital: Начальный капитал.
        """
        self.position_type: PositionType | None = None
        self.entry_price: float = 0.0
        self.entry_time = None
        self.entry_capital: float = 0.0
        self.initial_stop_loss: float = np.nan
        self.current_stop_loss: float = np.nan
        self.current_take_profit: float = np.nan
        self.current_capital: float = current_capital

    def has_position(self) -> bool:
        """Проверяет, есть ли открытая позиция."""
        return self.position_type is not None

    def reset_position(self) -> None:
        """Сбрасывает состояние позиции после закрытия."""
        self.position_type = None
        self.entry_price = 0.0
        self.entry_time = None
        self.entry_capital = 0.0
        self.initial_stop_loss = np.nan
        self.current_stop_loss = np.nan
        self.current_take_profit = np.nan


class ExitChecker:
    """
    Проверяет условия выхода из позиций.

    Определяет приоритеты выхода:
    1. Stop Loss - максимальный приоритет (ограничение убытков)
    2. Take Profit - средний приоритет (фиксация прибыли)
    3. Exit Signal - минимальный приоритет (сигнал стратегии)

    Attributes:
        correlation_id: ID корреляции для логирования.

    Examples:
        >>> checker = ExitChecker(correlation_id="test-123")
        >>> exit_info = checker.check_exit_conditions(state, cached, i)
        >>> if exit_info:
        ...     print(f"Exit reason: {exit_info.reason}")
    """

    def __init__(self, correlation_id: str | None = None):
        """
        Инициализирует проверщик выходов.

        Args:
            correlation_id: ID корреляции для трейсинга.
        """
        self.correlation_id = correlation_id

    def check_exit_conditions(
        self, state: TradingState, cached: CachedData, i: int
    ) -> ExitInfo | None:
        """
        Проверяет условия выхода из позиции.

        ПРИОРИТЕТЫ ВЫХОДА (в порядке убывания):
        1. Stop Loss - максимальный приоритет (ограничение убытков)
        2. Take Profit - средний приоритет (фиксация прибыли)
        3. Exit Signal - минимальный приоритет (сигнал стратегии)

        Args:
            state: Текущее состояние позиции.
            cached: Кэшированные данные.
            i: Индекс текущей свечи.

        Returns:
            ExitInfo если условие выхода сработало, иначе None.

        Examples:
            >>> state = TradingState()
            >>> state.position_type = PositionType.BUY
            >>> state.current_stop_loss = 95.0
            >>> # Если цена опустилась ниже SL
            >>> exit_info = checker.check_exit_conditions(state, cached, i)
            >>> assert exit_info.reason == ExitReason.STOP_LOSS
        """
        # Приоритет 1: Stop Loss
        if state.position_type == PositionType.BUY:
            if (
                not np.isnan(state.current_stop_loss)
                and cached.df_low[i] <= state.current_stop_loss
            ):
                return ExitInfo(
                    reason=ExitReason.STOP_LOSS,
                    price=state.current_stop_loss,
                )

        elif state.position_type == PositionType.SELL:
            if (
                not np.isnan(state.current_stop_loss)
                and cached.df_high[i] >= state.current_stop_loss
            ):
                return ExitInfo(
                    reason=ExitReason.STOP_LOSS,
                    price=state.current_stop_loss,
                )

        # Приоритет 2: Take Profit
        if state.position_type == PositionType.BUY:
            if (
                not np.isnan(state.current_take_profit)
                and cached.df_high[i] >= state.current_take_profit
            ):
                return ExitInfo(
                    reason=ExitReason.TAKE_PROFIT,
                    price=state.current_take_profit,
                )

        elif state.position_type == PositionType.SELL:
            if (
                not np.isnan(state.current_take_profit)
                and cached.df_low[i] <= state.current_take_profit
            ):
                return ExitInfo(
                    reason=ExitReason.TAKE_PROFIT,
                    price=state.current_take_profit,
                )

        # Приоритет 3: Exit Signal
        if (
            state.position_type == PositionType.BUY
            and cached.exit_long_signals[i]
        ):
            return ExitInfo(
                reason=ExitReason.EXIT_SIGNAL,
                price=cached.df_close[i],
            )

        elif (
            state.position_type == PositionType.SELL
            and cached.exit_short_signals[i]
        ):
            return ExitInfo(
                reason=ExitReason.EXIT_SIGNAL,
                price=cached.df_close[i],
            )

        return None

    def check_flip(
        self, state: TradingState, cached: CachedData, i: int
    ) -> bool:
        """
        Проверяет происходит ли флип (переворот) позиции.

        ФЛИП происходит когда одновременно:
        1. Закрывается текущая позиция (по SL/TP/Exit Signal)
        2. Есть сигнал на вход в ПРОТИВОПОЛОЖНУЮ позицию

        Args:
            state: Текущее состояние позиции.
            cached: Кэшированные данные.
            i: Индекс текущей свечи.

        Returns:
            True если происходит флип, иначе False.

        Examples:
            >>> # Закрываем Long и сразу открываем Short
            >>> is_flip = checker.check_flip(state, cached, i)
            >>> assert is_flip == True
        """
        if state.position_type == PositionType.BUY:
            return bool(cached.entry_sell_signals[i])
        elif state.position_type == PositionType.SELL:
            return bool(cached.entry_buy_signals[i])
        return False
