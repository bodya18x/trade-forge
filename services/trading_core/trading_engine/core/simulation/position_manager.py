"""
Position Manager - управление торговыми позициями.

Отвечает за:
- Открытие новых позиций
- Закрытие существующих позиций
- Обновление trailing stop loss
- Расчет take profit
"""

from __future__ import annotations

import numpy as np
from tradeforge_logger import get_logger

from core.common import ExitReason, PositionType
from core.simulation.data_cache import CachedData
from core.simulation.exit_checker import ExitInfo, TradingState
from core.simulation.trade_builder import TradeBuilder
from models.backtest import BacktestTrade
from models.strategy import StrategyDefinition, TakeProfitConfig

logger = get_logger(__name__)


class EntryInfo:
    """
    Информация о входе в позицию.

    Содержит все необходимые данные для открытия сделки.

    Attributes:
        position_type: Тип позиции (BUY/SELL).
        price: Цена входа.
        stop_loss: Уровень stop loss.
        take_profit: Уровень take profit.
    """

    __slots__ = ("position_type", "price", "stop_loss", "take_profit")

    def __init__(
        self,
        position_type: PositionType,
        price: float,
        stop_loss: float,
        take_profit: float,
    ):
        """
        Инициализирует информацию о входе.

        Args:
            position_type: Тип позиции для открытия.
            price: Цена входа в позицию.
            stop_loss: Начальный уровень SL.
            take_profit: Уровень TP.
        """
        self.position_type = position_type
        self.price = price
        self.stop_loss = stop_loss
        self.take_profit = take_profit


class PositionManager:
    """
    Менеджер торговых позиций для симуляции.

    Управляет жизненным циклом позиций:
    - Проверка условий входа и открытие позиций
    - Обновление trailing stop loss
    - Закрытие позиций и создание сделок

    Attributes:
        trade_builder: Builder для создания объектов BacktestTrade.
        strategy_definition: Определение стратегии для расчета TP.
        correlation_id: ID корреляции для логирования.

    Examples:
        >>> manager = PositionManager(trade_builder, strategy, "test-123")
        >>> entry_info = manager.check_entry_conditions(cached, i)
        >>> if entry_info:
        ...     manager.open_position(state, entry_info, cached, i)
    """

    def __init__(
        self,
        trade_builder: TradeBuilder,
        strategy_definition: StrategyDefinition,
        correlation_id: str | None = None,
    ):
        """
        Инициализирует менеджер позиций.

        Args:
            trade_builder: Builder для создания сделок.
            strategy_definition: Определение стратегии.
            correlation_id: ID корреляции для трейсинга.
        """
        self.trade_builder = trade_builder
        self.strategy_definition = strategy_definition
        self.correlation_id = correlation_id

    def check_entry_conditions(
        self, cached: CachedData, i: int
    ) -> EntryInfo | None:
        """
        Проверяет условия входа в новую позицию.

        Args:
            cached: Кэшированные данные.
            i: Индекс текущей свечи.

        Returns:
            EntryInfo если есть сигнал на вход, иначе None.

        Examples:
            >>> entry_info = manager.check_entry_conditions(cached, i)
            >>> if entry_info:
            ...     print(f"Entry signal: {entry_info.position_type}")
        """
        has_buy_signal = cached.entry_buy_signals[i]
        has_sell_signal = cached.entry_sell_signals[i]

        # Ambiguous signals
        if has_buy_signal and has_sell_signal:
            logger.warning(
                "position_manager.ambiguous_signals",
                timestamp=str(cached.df_index[i]),
                correlation_id=self.correlation_id,
            )
            return None

        # Entry BUY
        if has_buy_signal:
            sl_value = cached.sl_long_values[i]
            stop_loss = sl_value if not np.isnan(sl_value) else np.nan
            take_profit = self._calculate_take_profit(
                PositionType.BUY, cached.df_close[i], stop_loss
            )
            return EntryInfo(
                position_type=PositionType.BUY,
                price=cached.df_close[i],
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

        # Entry SELL
        elif has_sell_signal:
            sl_value = cached.sl_short_values[i]
            stop_loss = sl_value if not np.isnan(sl_value) else np.nan
            take_profit = self._calculate_take_profit(
                PositionType.SELL, cached.df_close[i], stop_loss
            )
            return EntryInfo(
                position_type=PositionType.SELL,
                price=cached.df_close[i],
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

        return None

    def open_position(
        self,
        state: TradingState,
        entry_info: EntryInfo,
        cached: CachedData,
        i: int,
    ) -> None:
        """
        Открывает новую позицию.

        Args:
            state: Текущее состояние позиции.
            entry_info: Информация о входе.
            cached: Кэшированные данные.
            i: Индекс текущей свечи.

        Examples:
            >>> entry_info = EntryInfo(PositionType.BUY, price=100.0, ...)
            >>> manager.open_position(state, entry_info, cached, i)
            >>> assert state.has_position() == True
        """
        state.position_type = entry_info.position_type
        state.entry_price = entry_info.price
        state.entry_time = cached.df_index[i]
        state.entry_capital = state.current_capital
        state.initial_stop_loss = entry_info.stop_loss
        state.current_stop_loss = entry_info.stop_loss
        state.current_take_profit = entry_info.take_profit

        logger.debug(
            "position_manager.position_opened",
            position_type=str(state.position_type),
            entry_price=float(entry_info.price),
            stop_loss=(
                float(entry_info.stop_loss)
                if not np.isnan(entry_info.stop_loss)
                else None
            ),
            take_profit=(
                float(entry_info.take_profit)
                if not np.isnan(entry_info.take_profit)
                else None
            ),
            timestamp=str(cached.df_index[i]),
            correlation_id=self.correlation_id,
        )

    def close_position(
        self,
        state: TradingState,
        exit_info: ExitInfo,
        cached: CachedData,
        i: int,
    ) -> BacktestTrade:
        """
        Закрывает текущую позицию и создает сделку.

        Args:
            state: Текущее состояние позиции.
            exit_info: Информация о выходе.
            cached: Кэшированные данные.
            i: Индекс текущей свечи.

        Returns:
            Созданная сделка BacktestTrade.

        Examples:
            >>> exit_info = ExitInfo(ExitReason.STOP_LOSS, price=95.0)
            >>> trade = manager.close_position(state, exit_info, cached, i)
            >>> assert trade.exit_reason == "Stop Loss"
        """
        trade = self.trade_builder.build_trade(
            position=state.position_type,
            entry_time=state.entry_time,
            entry_price=state.entry_price,
            exit_time=cached.df_index[i],
            exit_price=exit_info.price,
            current_capital=state.entry_capital,
            initial_stop_loss=state.initial_stop_loss,
            final_stop_loss=state.current_stop_loss,
            take_profit=state.current_take_profit,
            exit_reason=str(exit_info.reason)
            + (" (FLIP)" if exit_info.is_flip else ""),
        )

        # Обновляем капитал
        state.current_capital = trade.exit_capital

        if exit_info.is_flip:
            logger.debug(
                "position_manager.position_flipped",
                timestamp=str(cached.df_index[i]),
                from_position=str(state.position_type),
                to_position=str(
                    PositionType.SELL
                    if state.position_type == PositionType.BUY
                    else PositionType.BUY
                ),
                price=float(cached.df_close[i]),
                correlation_id=self.correlation_id,
            )

        logger.debug(
            "position_manager.position_closed",
            position_type=str(state.position_type),
            exit_reason=str(exit_info.reason),
            exit_price=float(exit_info.price),
            net_profit=float(trade.net_profit_abs),
            timestamp=str(cached.df_index[i]),
            correlation_id=self.correlation_id,
        )

        # Сбрасываем позицию
        state.reset_position()

        return trade

    def update_trailing_stop_loss(
        self, state: TradingState, cached: CachedData, i: int
    ) -> None:
        """
        Обновляет trailing stop loss для открытой позиции.

        ВАЖНО: SL может только "подтягиваться" в выгодную сторону, но не расширяться!
        - Для Long (BUY): SL может только РАСТИ (защищая прибыль)
        - Для Short (SELL): SL может только ПАДАТЬ (защищая прибыль)

        Args:
            state: Текущее состояние позиции.
            cached: Кэшированные данные.
            i: Индекс текущей свечи.

        Examples:
            >>> # Long позиция, SL подтягивается вверх
            >>> manager.update_trailing_stop_loss(state, cached, i)
            >>> assert state.current_stop_loss >= state.initial_stop_loss
        """
        if state.position_type == PositionType.BUY:
            new_sl_value = cached.sl_long_values[i]
            if not np.isnan(new_sl_value) and (
                np.isnan(state.current_stop_loss)
                or new_sl_value > state.current_stop_loss
            ):
                old_sl = state.current_stop_loss
                state.current_stop_loss = new_sl_value
                logger.debug(
                    "position_manager.trailing_sl_updated",
                    position_type="BUY",
                    old_sl=float(old_sl) if not np.isnan(old_sl) else None,
                    new_sl=float(new_sl_value),
                    timestamp=str(cached.df_index[i]),
                    correlation_id=self.correlation_id,
                )

        elif state.position_type == PositionType.SELL:
            new_sl_value = cached.sl_short_values[i]
            if not np.isnan(new_sl_value) and (
                np.isnan(state.current_stop_loss)
                or new_sl_value < state.current_stop_loss
            ):
                old_sl = state.current_stop_loss
                state.current_stop_loss = new_sl_value
                logger.debug(
                    "position_manager.trailing_sl_updated",
                    position_type="SELL",
                    old_sl=float(old_sl) if not np.isnan(old_sl) else None,
                    new_sl=float(new_sl_value),
                    timestamp=str(cached.df_index[i]),
                    correlation_id=self.correlation_id,
                )

    def close_final_position(
        self, state: TradingState, cached: CachedData
    ) -> BacktestTrade | None:
        """
        Закрывает последнюю открытую позицию в конце данных.

        Args:
            state: Текущее состояние позиции.
            cached: Кэшированные данные.

        Returns:
            BacktestTrade если позиция была открыта, иначе None.
        """
        if not state.has_position():
            return None

        trade = self.trade_builder.build_trade(
            position=state.position_type,
            entry_time=state.entry_time,
            entry_price=state.entry_price,
            exit_time=cached.df_index[-1],
            exit_price=cached.df_close[-1],
            current_capital=state.entry_capital,
            initial_stop_loss=state.initial_stop_loss,
            final_stop_loss=state.current_stop_loss,
            take_profit=state.current_take_profit,
            exit_reason=str(ExitReason.END_OF_DATA),
        )

        logger.debug(
            "position_manager.final_position_closed",
            position_type=str(state.position_type),
            net_profit=float(trade.net_profit_abs),
            correlation_id=self.correlation_id,
        )

        return trade

    def _calculate_take_profit(
        self,
        position_type: PositionType,
        entry_price: float,
        current_stop_loss: float,
    ) -> float:
        """
        Рассчитывает take profit для позиции на основе конфигурации стратегии.

        Args:
            position_type: Тип позиции (BUY/SELL).
            entry_price: Цена входа в позицию.
            current_stop_loss: Текущий уровень stop loss.

        Returns:
            Рассчитанный уровень take profit или np.nan если не настроен.

        Examples:
            >>> # TP на основе процента
            >>> tp = manager._calculate_take_profit(PositionType.BUY, 100.0, 95.0)
            >>> assert tp > 100.0  # TP выше входа для Long
        """
        if not self.strategy_definition.take_profit:
            return np.nan

        tp_config: TakeProfitConfig = self.strategy_definition.take_profit

        # PERCENTAGE: процент от цены входа
        if tp_config.type == "PERCENTAGE":
            pct = tp_config.percentage / 100.0
            if position_type == PositionType.BUY:
                return entry_price * (1 + pct)
            else:  # SELL
                return entry_price * (1 - pct)

        # RISK_REWARD: кратное отношение риска к прибыли
        elif tp_config.type == "RISK_REWARD" and not np.isnan(
            current_stop_loss
        ):
            risk = abs(entry_price - current_stop_loss)
            if position_type == PositionType.BUY:
                return entry_price + risk * tp_config.risk_reward_ratio
            else:  # SELL
                return entry_price - risk * tp_config.risk_reward_ratio

        return np.nan
