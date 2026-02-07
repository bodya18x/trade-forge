"""
Strategy Evaluator - векторизованный исполнитель торговых стратегий.

Главный координатор, делегирующий оценку конкретных типов узлов
специализированным evaluator'ам из подмодулей.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from tradeforge_logger import get_logger

from models.ast_nodes import AnyConditionNode, ResolvableValue
from models.strategy import StrategyDefinition

from .comparison import evaluate_comparison
from .crossover import evaluate_crossover
from .logical import evaluate_and, evaluate_or
from .special import evaluate_macd_crossover_flip, evaluate_super_trend_flip

logger = get_logger(__name__)


class StrategyEvaluator:
    """
    Векторизованный исполнитель логики торговой стратегии (AST).

    Координатор, делегирующий оценку узлов AST специализированным функциям.
    Использует паттерн "Стратегия" для диспетчеризации типов узлов.

    Attributes:
        definition: Определение стратегии (entry/exit условия).
        correlation_id: ID корреляции для логирования.

    Examples:
        >>> evaluator = StrategyEvaluator(strategy_definition, "test-123")
        >>> buy_signals, sell_signals = evaluator.evaluate_entry(df)
        >>> exit_long, exit_short = evaluator.evaluate_exit(df)
    """

    def __init__(
        self,
        strategy_definition: StrategyDefinition,
        correlation_id: str | None = None,
    ):
        """
        Инициализирует evaluator с определением стратегии.

        Args:
            strategy_definition: Определение стратегии с AST деревом.
            correlation_id: ID корреляции для логирования.
        """
        self.definition = strategy_definition
        self.correlation_id = correlation_id

        # Диспетчер для обработки типов узлов AST
        # Паттерн "Стратегия" - вместо длинной if-elif цепочки
        self._node_evaluators = {
            "AND": self._evaluate_and,
            "OR": self._evaluate_or,
            "GREATER_THAN": self._evaluate_comparison,
            "LESS_THAN": self._evaluate_comparison,
            "EQUALS": self._evaluate_comparison,
            "CROSSOVER_UP": self._evaluate_crossover,
            "CROSSOVER_DOWN": self._evaluate_crossover,
            "SUPER_TREND_FLIP": self._evaluate_super_trend_flip,
            "MACD_CROSSOVER_FLIP": self._evaluate_macd_crossover_flip,
        }

    def evaluate_entry(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """
        Оценивает условия входа для всего DataFrame.

        Использует DRY принцип через _evaluate_entry_side для обработки
        buy и sell сигналов единообразно.

        Args:
            df: DataFrame с OHLCV данными и индикаторами.

        Returns:
            Tuple (buy_signals, sell_signals) - булевы Series с сигналами.
        """
        # Проверка наличия условий входа
        if (
            self.definition.entry_buy_conditions is None
            and self.definition.entry_sell_conditions is None
        ):
            logger.warning(
                "evaluator.no_entry_conditions_defined",
                message="Strategy has no entry conditions - will generate no signals",
                correlation_id=self.correlation_id,
            )
            return pd.Series(False, index=df.index), pd.Series(
                False, index=df.index
            )

        # Оцениваем buy и sell сигналы через единый метод
        buy_signals = self._evaluate_entry_side(
            side="buy",
            conditions=self.definition.entry_buy_conditions,
            df=df,
        )

        sell_signals = self._evaluate_entry_side(
            side="sell",
            conditions=self.definition.entry_sell_conditions,
            df=df,
        )

        # Итоговое логирование
        logger.info(
            "evaluator.entry_signals_generated",
            buy_count=int(buy_signals.sum()),
            sell_count=int(sell_signals.sum()),
            correlation_id=self.correlation_id,
        )

        return buy_signals.fillna(False), sell_signals.fillna(False)

    def _evaluate_entry_side(
        self,
        side: str,
        conditions: AnyConditionNode | None,
        df: pd.DataFrame,
    ) -> pd.Series:
        """
        DRY helper для оценки условий входа для одной стороны (buy/sell).

        Устраняет дублирование кода между buy и sell логикой.

        Args:
            side: Сторона входа ("buy" или "sell").
            conditions: Узел условий для оценки или None.
            df: DataFrame с данными.

        Returns:
            Серия булевых сигналов для данной стороны.
        """
        if not conditions:
            logger.debug(
                f"evaluator.no_{side}_conditions",
                message=f"No {side} conditions defined",
                correlation_id=self.correlation_id,
            )
            return pd.Series(False, index=df.index)

        logger.debug(
            f"evaluator.evaluating_{side}_conditions",
            condition_type=conditions.type,
            correlation_id=self.correlation_id,
        )

        signals = self._evaluate_node(conditions, df)

        # Информируем если нет сигналов
        if signals.sum() == 0:
            logger.info(
                f"evaluator.no_{side}_signals_generated",
                message=f"No {side} signals in evaluated period",
                correlation_id=self.correlation_id,
            )

        return signals

    def evaluate_exit(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """
        Оценивает условия выхода из позиции для всего DataFrame.

        Args:
            df: DataFrame с данными.

        Returns:
            Tuple (exit_long_series, exit_short_series) - булевы Series.
        """
        exit_long_series = pd.Series(False, index=df.index)
        exit_short_series = pd.Series(False, index=df.index)

        if self.definition.exit_conditions:
            common_exit_long = self._evaluate_node(
                self.definition.exit_conditions, df, "BUY"
            )
            common_exit_short = self._evaluate_node(
                self.definition.exit_conditions, df, "SELL"
            )
            exit_long_series |= common_exit_long
            exit_short_series |= common_exit_short

        if self.definition.exit_long_conditions:
            specific_exit_long = self._evaluate_node(
                self.definition.exit_long_conditions, df, "BUY"
            )
            exit_long_series |= specific_exit_long

        if self.definition.exit_short_conditions:
            specific_exit_short = self._evaluate_node(
                self.definition.exit_short_conditions, df, "SELL"
            )
            exit_short_series |= specific_exit_short

        logger.debug(
            "evaluator.exit_signals_generated",
            long_exit_count=int(exit_long_series.sum()),
            short_exit_count=int(exit_short_series.sum()),
            correlation_id=self.correlation_id,
        )

        return exit_long_series.fillna(False), exit_short_series.fillna(False)

    def calculate_stop_loss_series(
        self, df: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        """
        Рассчитывает серии уровней Stop Loss для Long и Short позиций.

        Args:
            df: DataFrame с данными.

        Returns:
            Tuple (sl_long_series, sl_short_series).
        """
        sl_config = self.definition.stop_loss
        if not sl_config:
            return pd.Series(np.nan, index=df.index), pd.Series(
                np.nan, index=df.index
            )

        sl_type = sl_config.type
        if sl_type == "INDICATOR_BASED":
            sl_long = df.get(
                sl_config.buy_value_key, pd.Series(np.nan, index=df.index)
            )
            sl_short = df.get(
                sl_config.sell_value_key, pd.Series(np.nan, index=df.index)
            )
            return sl_long, sl_short

        elif sl_type == "PERCENTAGE" and sl_config.percentage:
            price_series = df["close"]
            pct = sl_config.percentage / 100.0
            sl_long = price_series * (1 - pct)
            sl_short = price_series * (1 + pct)
            return sl_long, sl_short

        return pd.Series(np.nan, index=df.index), pd.Series(
            np.nan, index=df.index
        )

    def calculate_take_profit_series(
        self, df: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        """
        Рассчитывает серии уровней Take Profit для Long и Short позиций.

        NOTE: Take Profit зависит от entry_price, который известен только
        после открытия позиции. Поэтому этот метод возвращает NaN серии.
        Реальный расчет TP происходит в executor при открытии позиции.

        Args:
            df: DataFrame с данными.

        Returns:
            Tuple (tp_long_series, tp_short_series) - всегда NaN серии.
        """
        # TP рассчитывается динамически в executor на основе entry_price
        return pd.Series(np.nan, index=df.index), pd.Series(
            np.nan, index=df.index
        )

    def _resolve_value(
        self, value_node: ResolvableValue, df: pd.DataFrame
    ) -> pd.Series:
        """
        Извлекает временной ряд (Series) на основе узла AST.

        Преобразует узел типа VALUE/INDICATOR_VALUE/PREV_INDICATOR_VALUE
        в pandas Series для векторизованных операций.

        Args:
            value_node: Узел AST представляющий значение.
            df: DataFrame с данными свечей и индикаторов.

        Returns:
            Серия значений для всех свечей.
        """
        if value_node.type == "VALUE":
            # Константа - создаем серию с одинаковым значением
            return pd.Series(value_node.value, index=df.index)

        key = value_node.key

        if value_node.type == "PREV_INDICATOR_VALUE":
            # shift(1) сдвигает серию: значение на индексе i становится значением с i-1
            # Это нужно для стратегий типа "RSI на ПРЕДЫДУЩЕЙ свече был > 70"
            series = df.get(key, pd.Series(np.nan, index=df.index))

            if key not in df.columns:
                logger.warning(
                    "evaluator.indicator_column_not_found",
                    key=key,
                    value_type="PREV_INDICATOR_VALUE",
                    available_columns_sample=list(df.columns)[:10],
                    correlation_id=self.correlation_id,
                )

            return series.shift(1)

        if value_node.type == "INDICATOR_VALUE":
            series = df.get(key, pd.Series(np.nan, index=df.index))

            if key not in df.columns:
                logger.warning(
                    "evaluator.indicator_column_not_found",
                    key=key,
                    value_type="INDICATOR_VALUE",
                    available_columns_sample=list(df.columns)[:10],
                    correlation_id=self.correlation_id,
                )

            return series

        logger.warning(
            "evaluator.unknown_value_node_type",
            node_type=value_node.type,
            correlation_id=self.correlation_id,
        )
        return pd.Series(np.nan, index=df.index)

    def _evaluate_node(
        self,
        node: AnyConditionNode,
        df: pd.DataFrame,
        position_dir: str | None = None,
    ) -> pd.Series:
        """
        Рекурсивно вычисляет узел AST, возвращая булеву pd.Series.

        Использует паттерн "Стратегия" (Strategy Pattern) для диспетчеризации
        различных типов узлов к соответствующим методам-обработчикам.

        Args:
            node: Узел AST для вычисления.
            df: DataFrame с данными свечей и индикаторов.
            position_dir: Направление позиции ("BUY" или "SELL"), опционально.

        Returns:
            Булева серия с результатом вычисления условия для каждой свечи.
        """
        node_type = node.type

        # Диспетчеризация через словарь вместо длинной if-elif цепочки
        evaluator = self._node_evaluators.get(node_type)

        if not evaluator:
            logger.warning(
                "evaluator.unknown_node_type",
                node_type=node_type,
                correlation_id=self.correlation_id,
            )
            return pd.Series(False, index=df.index)

        return evaluator(node, df, position_dir)

    # === Методы-обертки для делегирования в специализированные модули ===

    def _evaluate_and(
        self,
        node: AnyConditionNode,
        df: pd.DataFrame,
        position_dir: str | None,
    ) -> pd.Series:
        """Делегирует оценку AND в logical.evaluate_and."""
        return evaluate_and(node, df, self._evaluate_node, position_dir)

    def _evaluate_or(
        self,
        node: AnyConditionNode,
        df: pd.DataFrame,
        position_dir: str | None,
    ) -> pd.Series:
        """Делегирует оценку OR в logical.evaluate_or."""
        return evaluate_or(node, df, self._evaluate_node, position_dir)

    def _evaluate_comparison(
        self,
        node: AnyConditionNode,
        df: pd.DataFrame,
        position_dir: str | None,
    ) -> pd.Series:
        """Делегирует оценку comparison в comparison.evaluate_comparison."""
        return evaluate_comparison(node, df, self._resolve_value, position_dir)

    def _evaluate_crossover(
        self,
        node: AnyConditionNode,
        df: pd.DataFrame,
        position_dir: str | None,
    ) -> pd.Series:
        """Делегирует оценку crossover в crossover.evaluate_crossover."""
        return evaluate_crossover(node, df, self._resolve_value, position_dir)

    def _evaluate_super_trend_flip(
        self,
        node: AnyConditionNode,
        df: pd.DataFrame,
        position_dir: str | None,
    ) -> pd.Series:
        """Делегирует оценку SuperTrend flip в special.evaluate_super_trend_flip."""
        return evaluate_super_trend_flip(
            node, df, position_dir, self.correlation_id
        )

    def _evaluate_macd_crossover_flip(
        self,
        node: AnyConditionNode,
        df: pd.DataFrame,
        position_dir: str | None,
    ) -> pd.Series:
        """Делегирует оценку MACD flip в special.evaluate_macd_crossover_flip."""
        return evaluate_macd_crossover_flip(
            node, df, position_dir, self.correlation_id
        )
