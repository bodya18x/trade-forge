"""
Special Evaluators - специализированные evaluator'ы для индикаторов.

Содержит evaluator'ы для специфичных индикаторов:
- SUPER_TREND_FLIP: переворот направления SuperTrend
- MACD_CROSSOVER_FLIP: кроссовер MACD line и Signal line
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
from tradeforge_logger import get_logger

if TYPE_CHECKING:
    from models.ast_nodes import AnyConditionNode

logger = get_logger(__name__)


def evaluate_super_trend_flip(
    node: AnyConditionNode,
    df: pd.DataFrame,
    position_dir: str | None,
    correlation_id: str | None = None,
) -> pd.Series:
    """
    Оценивает узел SUPER_TREND_FLIP - переворот SuperTrend индикатора.

    Проверяет изменение направления SuperTrend с учетом текущей позиции:
    - Для BUY позиции: выход при развороте вниз (1 -> -1)
    - Для SELL позиции: выход при развороте вверх (-1 -> 1)

    Args:
        node: Узел типа SUPER_TREND_FLIP с indicator_key.
        df: DataFrame с данными.
        position_dir: Направление позиции ("BUY" или "SELL").
        correlation_id: ID корреляции для логирования.

    Returns:
        Результат проверки флипа (pd.Series[bool]).
    """
    if not position_dir:
        logger.debug(
            "evaluator.super_trend_flip_no_position_dir",
            indicator_key=node.indicator_key,
            correlation_id=correlation_id,
        )
        return pd.Series(False, index=df.index)

    direction_series = df.get(node.indicator_key)
    if direction_series is None:
        logger.warning(
            "evaluator.super_trend_direction_not_found",
            indicator_key=node.indicator_key,
            position_dir=position_dir,
            available_columns_sample=list(df.columns)[:10],
            correlation_id=correlation_id,
        )
        return pd.Series(False, index=df.index)

    prev_direction = direction_series.shift(1)

    # Проверяем переворот в зависимости от типа позиции
    if position_dir == "BUY":
        # Выход из лонга: переворот вниз (1 -> -1)
        result = (prev_direction == 1) & (direction_series == -1)
    elif position_dir == "SELL":
        # Выход из шорта: переворот вверх (-1 -> 1)
        result = (prev_direction == -1) & (direction_series == 1)
    else:
        result = pd.Series(False, index=df.index)

    return result


def evaluate_macd_crossover_flip(
    node: AnyConditionNode,
    df: pd.DataFrame,
    position_dir: str | None,
    correlation_id: str | None = None,
) -> pd.Series:
    """
    Оценивает узел MACD_CROSSOVER_FLIP - кроссовер MACD линий.

    Проверяет пересечение MACD line и Signal line для выхода из позиции:
    - Для BUY: выход когда MACD пересекает Signal сверху вниз (медвежий)
    - Для SELL: выход когда MACD пересекает Signal снизу вверх (бычий)

    Args:
        node: Узел типа MACD_CROSSOVER_FLIP с macd_line_key и signal_line_key.
        df: DataFrame с данными.
        position_dir: Направление позиции ("BUY" или "SELL").
        correlation_id: ID корреляции для логирования.

    Returns:
        Булева серия с True на свечах где произошел кроссовер.
    """
    if not position_dir:
        logger.debug(
            "evaluator.macd_crossover_flip_no_position_dir",
            macd_line_key=getattr(node, "macd_line_key", None),
            signal_line_key=getattr(node, "signal_line_key", None),
            correlation_id=correlation_id,
        )
        return pd.Series(False, index=df.index)

    # Получаем ключи из узла
    macd_line_key = getattr(node, "macd_line_key", None)
    signal_line_key = getattr(node, "signal_line_key", None)

    if not macd_line_key or not signal_line_key:
        logger.warning(
            "evaluator.macd_keys_not_provided",
            macd_line_key=macd_line_key,
            signal_line_key=signal_line_key,
            correlation_id=correlation_id,
        )
        return pd.Series(False, index=df.index)

    # Получаем серии из DataFrame
    macd_line = df.get(macd_line_key)
    signal_line = df.get(signal_line_key)

    if macd_line is None or signal_line is None:
        logger.warning(
            "evaluator.macd_lines_not_found",
            macd_line_key=macd_line_key,
            signal_line_key=signal_line_key,
            macd_found=macd_line is not None,
            signal_found=signal_line is not None,
            available_columns_sample=list(df.columns)[:10],
            correlation_id=correlation_id,
        )
        return pd.Series(False, index=df.index)

    # Получаем предыдущие значения
    macd_line_prev = macd_line.shift(1)
    signal_line_prev = signal_line.shift(1)

    # Проверяем кроссовер в зависимости от типа позиции
    if position_dir == "BUY":
        # Выход из лонга: MACD пересекает Signal сверху вниз (медвежий)
        result = (macd_line_prev >= signal_line_prev) & (
            macd_line < signal_line
        )
    elif position_dir == "SELL":
        # Выход из шорта: MACD пересекает Signal снизу вверх (бычий)
        result = (macd_line_prev <= signal_line_prev) & (
            macd_line > signal_line
        )
    else:
        result = pd.Series(False, index=df.index)

    return result
