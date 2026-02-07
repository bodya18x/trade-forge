"""
Crossover Evaluators - оценка кроссоверов линий.

Содержит evaluator'ы для пересечения линий:
- CROSSOVER_UP: line1 пересекает line2 снизу вверх (золотой крест)
- CROSSOVER_DOWN: line1 пересекает line2 сверху вниз (мертвый крест)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from models.ast_nodes import AnyConditionNode


def evaluate_crossover(
    node: AnyConditionNode,
    df: pd.DataFrame,
    resolve_value_fn,
    position_dir: str | None,
) -> pd.Series:
    """
    Оценивает узлы кроссовера: CROSSOVER_UP, CROSSOVER_DOWN.

    Кроссовер - момент пересечения двух линий.

    CROSSOVER_UP (золотой крест):
    - Было: line1 <= line2 (быстрая линия была ниже медленной)
    - Стало: line1 > line2 (быстрая линия стала выше)

    CROSSOVER_DOWN (мертвый крест):
    - Было: line1 >= line2 (быстрая линия была выше медленной)
    - Стало: line1 < line2 (быстрая линия стала ниже)

    Args:
        node: Узел типа CROSSOVER с атрибутами line1 и line2.
        df: DataFrame с данными.
        resolve_value_fn: Функция для резолва значений линий.
        position_dir: Направление позиции (не используется).

    Returns:
        Результат проверки кроссовера (pd.Series[bool]).

    Examples:
        >>> # EMA(12) пересекла EMA(50) снизу вверх
        >>> node = CrossoverNode(type="CROSSOVER_UP", line1=ema12, line2=ema50)
        >>> signals = evaluate_crossover(node, df, resolve_fn, None)
    """
    line1 = resolve_value_fn(node.line1, df)
    line2 = resolve_value_fn(node.line2, df)
    line1_prev = line1.shift(1)
    line2_prev = line2.shift(1)

    if node.type == "CROSSOVER_UP":
        # Предыдущее: line1 <= line2, Текущее: line1 > line2
        return (line1_prev <= line2_prev) & (line1 > line2)
    elif node.type == "CROSSOVER_DOWN":
        # Предыдущее: line1 >= line2, Текущее: line1 < line2
        return (line1_prev >= line2_prev) & (line1 < line2)
    else:
        return pd.Series(False, index=df.index)
