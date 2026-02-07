"""
Data Transformer для преобразования индикаторов в long format.

Трансформирует широкий DataFrame (OHLCV + indicators) в длинный формат
для эффективного хранения в ClickHouse ReplacingMergeTree.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from tradeforge_logger import get_logger

from calc.base import BaseIndicator
from core.constants import INDICATOR_VALUE_SEPARATOR
from core.timezone_utils import ensure_moscow_tz

logger = get_logger(__name__)


class DataTransformer:
    """
    Трансформирует данные индикаторов в long format.

    Long format schema:
        (ticker, timeframe, begin, indicator_key, value_key, value)

    Преобразует широкий DataFrame где каждый индикатор - отдельная колонка
    в узкий формат где каждая строка - это одно значение индикатора.
    """

    @staticmethod
    def transform_single_indicator(
        df: pd.DataFrame,
        indicator: BaseIndicator,
        ticker: str,
        timeframe: str,
        original_start_date: datetime,
    ) -> pd.DataFrame:
        """
        Трансформирует один индикатор в long format.

        Args:
            df: DataFrame с рассчитанным индикатором.
            indicator: Объект индикатора.
            ticker: Тикер инструмента.
            timeframe: Таймфрейм.
            original_start_date: Дата начала без lookback периода.

        Returns:
            DataFrame в long format с колонками:
                [ticker, timeframe, begin, indicator_key, value_key, value].
        """
        df = df.copy()
        df["ticker"] = ticker
        df["timeframe"] = timeframe

        base_key = indicator.get_base_key()

        id_vars = ["ticker", "timeframe", "begin"]
        value_vars = []
        rename_map = {}

        for value_key, full_col_name in indicator.outputs.items():
            if full_col_name in df.columns:
                value_vars.append(full_col_name)
                rename_map[full_col_name] = (
                    f"{base_key}{INDICATOR_VALUE_SEPARATOR}{value_key}"
                )

        if not value_vars:
            logger.warning(
                "data_transformer.no_columns",
                indicator_key=base_key,
                ticker=ticker,
                timeframe=timeframe,
            )
            return pd.DataFrame()

        df_to_melt = df[id_vars + value_vars].copy()
        df_to_melt.rename(columns=rename_map, inplace=True)

        long_df = df_to_melt.melt(
            id_vars=id_vars,
            value_vars=rename_map.values(),
            var_name="temp_key",
            value_name="value",
        )

        long_df.dropna(subset=["value"], inplace=True)
        if long_df.empty:
            return pd.DataFrame()

        key_split = long_df["temp_key"].str.split(
            INDICATOR_VALUE_SEPARATOR, expand=True
        )
        long_df["indicator_key"] = key_split[0]
        long_df["value_key"] = key_split[1]
        long_df.drop(columns=["temp_key"], inplace=True)

        original_start = ensure_moscow_tz(original_start_date)
        long_df = long_df[long_df["begin"] >= original_start]

        logger.debug(
            "data_transformer.transformed",
            ticker=ticker,
            timeframe=timeframe,
            indicator_key=base_key,
            records_count=len(long_df),
        )

        return long_df
