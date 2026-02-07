"""
Comparison Evaluators - оценка операторов сравнения.

Содержит evaluator'ы для сравнения значений:
- GREATER_THAN (>)
- LESS_THAN (<)
- EQUALS (==)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from models.ast_nodes import AnyConditionNode


def evaluate_comparison(
    node: AnyConditionNode,
    df: pd.DataFrame,
    resolve_value_fn,
    position_dir: str | None,
) -> pd.Series:
    """
    Оценивает узлы сравнения: GREATER_THAN, LESS_THAN, EQUALS.

    Args:
        node: Узел типа сравнения с атрибутами left и right.
        df: DataFrame с данными.
        resolve_value_fn: Функция для резолва значений (VALUE/INDICATOR_VALUE).
        position_dir: Направление позиции (не используется).

    Returns:
        Результат сравнения (pd.Series[bool]).
    """
    left_series = resolve_value_fn(node.left, df)
    right_series = resolve_value_fn(node.right, df)

    # Выполняем сравнение в зависимости от типа
    if node.type == "GREATER_THAN":
        result = left_series > right_series
    elif node.type == "LESS_THAN":
        result = left_series < right_series
    elif node.type == "EQUALS":
        # np.isclose возвращает ndarray, оборачиваем в Series
        result = pd.Series(
            np.isclose(left_series, right_series), index=df.index
        )
    else:
        result = pd.Series(False, index=df.index)

    return result
