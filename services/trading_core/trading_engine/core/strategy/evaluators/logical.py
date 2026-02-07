"""
Logical Evaluators - оценка логических операторов AND/OR.

Содержит evaluator'ы для булевых операций над условиями.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from models.ast_nodes import AnyConditionNode


def evaluate_and(
    node: AnyConditionNode,
    df: pd.DataFrame,
    evaluate_node_fn,
    position_dir: str | None,
) -> pd.Series:
    """
    Оценивает узел AND - логическое И.

    Все дочерние условия должны быть True.

    Args:
        node: Узел типа AND с списком conditions.
        df: DataFrame с данными.
        evaluate_node_fn: Функция для рекурсивной оценки дочерних узлов.
        position_dir: Направление позиции.

    Returns:
        Результат AND операции (pd.Series[bool]).
    """
    result = pd.Series(True, index=df.index)
    for cond in node.conditions:
        result &= evaluate_node_fn(cond, df, position_dir)
    return result


def evaluate_or(
    node: AnyConditionNode,
    df: pd.DataFrame,
    evaluate_node_fn,
    position_dir: str | None,
) -> pd.Series:
    """
    Оценивает узел OR - логическое ИЛИ.

    Хотя бы одно дочернее условие должно быть True.

    Args:
        node: Узел типа OR с списком conditions.
        df: DataFrame с данными.
        evaluate_node_fn: Функция для рекурсивной оценки дочерних узлов.
        position_dir: Направление позиции.

    Returns:
        Результат OR операции (pd.Series[bool]).
    """
    result = pd.Series(False, index=df.index)
    for cond in node.conditions:
        result |= evaluate_node_fn(cond, df, position_dir)
    return result
