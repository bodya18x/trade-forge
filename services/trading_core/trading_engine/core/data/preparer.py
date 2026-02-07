"""
Data Preparer для подготовки DataFrame для бэктеста.

Преобразует "длинные" списки данных из ClickHouse в один "широкий" DataFrame.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from tradeforge_logger import get_logger

from core.common import CLICKHOUSE_TECHNICAL_COLUMNS, InsufficientDataError

logger = get_logger(__name__)


def prepare_dataframe(
    base_candles_list: list[dict[str, Any]],
    indicators_list: list[dict[str, Any]],
    correlation_id: str | None = None,
) -> pd.DataFrame:
    """
    Преобразует данные из ClickHouse в DataFrame для бэктеста.

    Объединяет базовые OHLCV свечи с индикаторами в один "широкий" DataFrame,
    где каждая строка - это свеча со всеми её индикаторами.

    Args:
        base_candles_list: Список свечей из ClickHouse (OHLCV данные).
        indicators_list: Список индикаторов из ClickHouse (длинный формат).
        correlation_id: ID корреляции для трейсинга.

    Returns:
        DataFrame с индексом по времени (begin) и колонками:
        - ticker, timeframe, open, high, low, close, volume
        - <indicator_key>_<value_key> для каждого индикатора

    Raises:
        InsufficientDataError: Если список свечей пустой или отсутствуют
            обязательные колонки (ticker, timeframe, begin, OHLCV).
        InsufficientDataError: Если не удалось преобразовать индикаторы
            в pivot table (некорректные данные в ClickHouse).
    """
    logger.info(
        "data_preparer.started",
        candles_count=len(base_candles_list),
        indicators_count=len(indicators_list),
        correlation_id=correlation_id,
    )

    if not base_candles_list:
        logger.info(
            "data_preparer.empty_candles_list",
            correlation_id=correlation_id,
        )
        raise InsufficientDataError(
            "Список свечей не может быть пустым для бэктеста"
        )

    required_cols = [
        "ticker",
        "timeframe",
        "begin",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    if base_candles_list and not all(
        k in base_candles_list[0] for k in required_cols
    ):
        missing = [k for k in required_cols if k not in base_candles_list[0]]
        logger.error(
            "data_preparer.missing_required_columns",
            missing_columns=missing,
            available_columns=list(base_candles_list[0].keys()),
            correlation_id=correlation_id,
        )
        raise InsufficientDataError(
            f"Отсутствуют обязательные колонки: {missing}"
        )

    base_df = pd.DataFrame(base_candles_list)
    base_df["begin"] = pd.to_datetime(base_df["begin"])
    base_df.set_index("begin", inplace=True)
    base_df.drop(
        columns=CLICKHOUSE_TECHNICAL_COLUMNS,
        inplace=True,
        errors="ignore",
    )

    if not indicators_list:
        logger.debug(
            "data_preparer.empty_indicators_list",
            correlation_id=correlation_id,
        )
        return base_df.sort_index()

    indicators_df = pd.DataFrame(indicators_list)
    indicators_df["begin"] = pd.to_datetime(indicators_df["begin"])
    indicators_df["full_key"] = (
        indicators_df["indicator_key"] + "_" + indicators_df["value_key"]
    )

    # Информируем о найденных индикаторах
    unique_indicators = indicators_df["full_key"].unique()
    logger.info(
        "data_preparer.unique_indicators_found",
        unique_count=len(unique_indicators),
        correlation_id=correlation_id,
    )

    try:
        pivoted_df = indicators_df.pivot_table(
            index="begin", columns="full_key", values="value"
        )
    except Exception as e:
        logger.exception(
            "data_preparer.pivot_failed",
            error=str(e),
            indicators_sample=indicators_df.head(5).to_dict("records"),
            correlation_id=correlation_id,
        )
        raise InsufficientDataError(
            f"Не удалось преобразовать данные индикаторов в pivot table: {e}. "
            "Проверьте корректность данных в ClickHouse."
        ) from e

    final_df = base_df.join(pivoted_df, how="left")

    for col in ["open", "high", "low", "close", "volume"]:
        if col in final_df.columns:
            final_df[f"{col}_value"] = final_df[col]

    final_df.sort_index(inplace=True)

    logger.info(
        "data_preparer.dataframe_prepared",
        rows=final_df.shape[0],
        columns=final_df.shape[1],
        correlation_id=correlation_id,
    )

    return final_df
