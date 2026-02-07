"""
Data Cache Manager - кэширование numpy массивов для оптимизации симуляции.

Предоставляет быстрый доступ к часто используемым данным через numpy массивы,
что на 10-20% быстрее чем доступ через pandas .iloc[i].
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from tradeforge_logger import get_logger

from core.simulation.signal_calculator import SignalsBatch

logger = get_logger(__name__)


class CachedData:
    """
    Кэшированные numpy массивы для оптимизации доступа к данным.

    ОПТИМИЗАЦИЯ: Прямой доступ к numpy массивам быстрее чем .iloc[i] на ~10-20%.

    Attributes:
        df_low: Массив цен Low.
        df_high: Массив цен High.
        df_close: Массив цен Close.
        df_index: Индекс DataFrame (временные метки).
        entry_buy_signals: Массив сигналов на вход в Long.
        entry_sell_signals: Массив сигналов на вход в Short.
        exit_long_signals: Массив сигналов на выход из Long.
        exit_short_signals: Массив сигналов на выход из Short.
        sl_long_values: Массив значений Stop Loss для Long.
        sl_short_values: Массив значений Stop Loss для Short.

    Examples:
        >>> cached = CachedData(...)
        >>> # Быстрый доступ к данным
        >>> current_price = cached.df_close[i]
        >>> has_buy_signal = cached.entry_buy_signals[i]
    """

    __slots__ = (
        "df_low",
        "df_high",
        "df_close",
        "df_index",
        "entry_buy_signals",
        "entry_sell_signals",
        "exit_long_signals",
        "exit_short_signals",
        "sl_long_values",
        "sl_short_values",
    )

    def __init__(
        self,
        df_low: np.ndarray,
        df_high: np.ndarray,
        df_close: np.ndarray,
        df_index: pd.Index,
        entry_buy_signals: np.ndarray,
        entry_sell_signals: np.ndarray,
        exit_long_signals: np.ndarray,
        exit_short_signals: np.ndarray,
        sl_long_values: np.ndarray,
        sl_short_values: np.ndarray,
    ):
        """
        Инициализирует кэш данных.

        Args:
            df_low: Массив минимальных цен.
            df_high: Массив максимальных цен.
            df_close: Массив цен закрытия.
            df_index: Временные метки свечей.
            entry_buy_signals: Массив bool сигналов на покупку.
            entry_sell_signals: Массив bool сигналов на продажу.
            exit_long_signals: Массив bool сигналов на выход из лонга.
            exit_short_signals: Массив bool сигналов на выход из шорта.
            sl_long_values: Массив float уровней SL для лонга.
            sl_short_values: Массив float уровней SL для шорта.
        """
        self.df_low = df_low
        self.df_high = df_high
        self.df_close = df_close
        self.df_index = df_index
        self.entry_buy_signals = entry_buy_signals
        self.entry_sell_signals = entry_sell_signals
        self.exit_long_signals = exit_long_signals
        self.exit_short_signals = exit_short_signals
        self.sl_long_values = sl_long_values
        self.sl_short_values = sl_short_values


class DataCacheManager:
    """
    Менеджер кэширования данных для быстрого доступа в цикле симуляции.

    Конвертирует pandas Series в numpy массивы для ускорения
    доступа к элементам в пошаговой симуляции.

    Examples:
        >>> manager = DataCacheManager()
        >>> cached = manager.cache_data_arrays(df, signals)
        >>> # Теперь можно быстро получать данные по индексу
        >>> price = cached.df_close[i]  # Быстрее чем df['close'].iloc[i]
    """

    @staticmethod
    def cache_data_arrays(
        df: pd.DataFrame, signals: SignalsBatch
    ) -> CachedData:
        """
        Кэширует numpy массивы для быстрого доступа в цикле симуляции.

        Args:
            df: DataFrame с OHLCV данными.
            signals: Пакет сигналов для бэктеста.

        Returns:
            CachedData с numpy массивами.

        Raises:
            KeyError: Если в DataFrame отсутствуют обязательные колонки.

        Examples:
            >>> df = pd.DataFrame({'close': [100, 101, 102], ...})
            >>> signals = SignalsBatch(...)
            >>> cached = DataCacheManager.cache_data_arrays(df, signals)
            >>> assert isinstance(cached.df_close, np.ndarray)
        """
        logger.debug(
            "data_cache.caching_arrays",
            rows=len(df),
            columns=len(df.columns),
        )

        cached = CachedData(
            df_low=df["low"].values,
            df_high=df["high"].values,
            df_close=df["close"].values,
            df_index=df.index,
            entry_buy_signals=signals.entry_buy.values,
            entry_sell_signals=signals.entry_sell.values,
            exit_long_signals=signals.exit_long.values,
            exit_short_signals=signals.exit_short.values,
            sl_long_values=signals.sl_long.values,
            sl_short_values=signals.sl_short.values,
        )

        logger.debug(
            "data_cache.arrays_cached",
            array_length=len(cached.df_close),
        )

        return cached
