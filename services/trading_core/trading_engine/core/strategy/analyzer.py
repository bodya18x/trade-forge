"""
Strategy Analyzer - анализ стратегий и извлечение индикаторов из AST.

Отвечает за:
1. Рекурсивный обход AST дерева стратегии
2. Извлечение всех используемых индикаторов
3. Парсинг full_key в (base_key, value_key) пары
"""

from __future__ import annotations

from tradeforge_logger import get_logger

from core.common import OHLCV_COLUMNS
from models.strategy import StrategyDefinition
from repositories.postgres import IndicatorRepository

logger = get_logger(__name__)


class StrategyAnalyzer:
    """
    Анализирует стратегию и извлекает требуемые индикаторы.

    Используется для определения, какие индикаторы нужно загрузить
    из БД перед выполнением бэктеста.

    Attributes:
        indicator_repo: Репозиторий для доступа к реестру индикаторов.
    """

    def __init__(self, indicator_repo: IndicatorRepository):
        """
        Инициализирует StrategyAnalyzer.

        Args:
            indicator_repo: Репозиторий индикаторов для загрузки реестра.
        """
        self.indicator_repo = indicator_repo

    async def extract_required_indicators(
        self, strategy: StrategyDefinition
    ) -> list[tuple[str, str]]:
        """
        Извлекает список требуемых индикаторов из стратегии.

        Универсальный подход:
        1. Собирает полные ключи (full_keys) из AST
        2. Загружает реестр индикаторов из PostgreSQL
        3. Парсит каждый full_key в (base_key, value_key) используя реестр

        Args:
            strategy: Определение стратегии.

        Returns:
            Список пар (indicator_key, value_key).
            Например: [("rsi_timeperiod_14", "value"), ("ema_timeperiod_50", "value")]

        Examples:
            >>> analyzer = StrategyAnalyzer(indicator_repo)
            >>> strategy = StrategyDefinition(
            ...     entry_buy_conditions=ConditionNode(
            ...         type="GREATER_THAN",
            ...         left={"type": "INDICATOR_VALUE", "key": "rsi_timeperiod_14_value"},
            ...         right={"type": "VALUE", "value": 30}
            ...     )
            ... )
            >>> indicators = await analyzer.extract_required_indicators(strategy)
            >>> print(indicators)
            [("rsi_timeperiod_14", "value")]
        """
        # Этап 1: Собираем полные ключи из AST
        full_keys = self._extract_full_keys_from_strategy(strategy)

        # Этап 2: Загружаем реестр индикаторов из PostgreSQL
        registry = await self.indicator_repo.get_full_indicator_registry()
        known_base_keys = list(registry.keys())

        # Этап 3: Парсим full_keys в (base_key, value_key) пары
        required_indicators = self._parse_full_keys(full_keys, known_base_keys)

        logger.debug(
            "strategy_analyzer.indicators_extracted",
            full_keys_count=len(full_keys),
            full_keys_sample=sorted(list(full_keys))[:10],
            parsed_indicators_count=len(required_indicators),
        )

        return sorted(list(required_indicators))

    def _extract_full_keys_from_strategy(
        self, strategy: StrategyDefinition
    ) -> set[str]:
        """
        Рекурсивно обходит AST дерево стратегии и собирает все используемые ключи индикаторов.

        Args:
            strategy: Определение стратегии.

        Returns:
            Множество полных ключей индикаторов (full_keys).
        """
        full_keys = set()

        def extract_from_node(node):
            """Рекурсивная функция для обхода AST узла."""
            if node is None:
                return

            if not hasattr(node, "type"):
                return

            node_type = node.type

            # 1. INDICATOR_VALUE, PREV_INDICATOR_VALUE - просто добавляем key
            if node_type in ["INDICATOR_VALUE", "PREV_INDICATOR_VALUE"]:
                full_keys.add(node.key)

            # 2. AND, OR - рекурсия по всем условиям
            elif node_type in ["AND", "OR"]:
                for cond in node.conditions:
                    extract_from_node(cond)

            # 3. GREATER_THAN, LESS_THAN, EQUALS - рекурсия по left и right
            elif node_type in ["GREATER_THAN", "LESS_THAN", "EQUALS"]:
                if hasattr(node, "left"):
                    extract_from_node(node.left)
                if hasattr(node, "right"):
                    extract_from_node(node.right)

            # 4. CROSSOVER_UP, CROSSOVER_DOWN - рекурсия по line1 и line2
            elif node_type in ["CROSSOVER_UP", "CROSSOVER_DOWN"]:
                if hasattr(node, "line1"):
                    extract_from_node(node.line1)
                if hasattr(node, "line2"):
                    extract_from_node(node.line2)

            # 5. SUPER_TREND_FLIP - добавляем indicator_key
            elif node_type == "SUPER_TREND_FLIP":
                if hasattr(node, "indicator_key") and node.indicator_key:
                    full_keys.add(node.indicator_key)

            # 6. MACD_CROSSOVER_FLIP - добавляем indicator_key и signal_key
            elif node_type == "MACD_CROSSOVER_FLIP":
                if hasattr(node, "indicator_key") and node.indicator_key:
                    full_keys.add(node.indicator_key)
                if hasattr(node, "signal_key") and node.signal_key:
                    full_keys.add(node.signal_key)

        # Извлекаем из всех секций стратегии
        extract_from_node(strategy.entry_buy_conditions)
        extract_from_node(strategy.entry_sell_conditions)
        extract_from_node(strategy.exit_conditions)
        extract_from_node(strategy.exit_long_conditions)
        extract_from_node(strategy.exit_short_conditions)

        # Извлекаем из stop_loss конфигурации
        if strategy.stop_loss and strategy.stop_loss.type == "INDICATOR_BASED":
            if strategy.stop_loss.buy_value_key:
                full_keys.add(strategy.stop_loss.buy_value_key)
            if strategy.stop_loss.sell_value_key:
                full_keys.add(strategy.stop_loss.sell_value_key)

        return full_keys

    def _parse_full_keys(
        self, full_keys: set[str], known_base_keys: list[str]
    ) -> set[tuple[str, str]]:
        """
        Парсит полные ключи индикаторов в пары (base_key, value_key).

        Например: "rsi_timeperiod_14_value" → ("rsi_timeperiod_14", "value")

        Args:
            full_keys: Множество полных ключей индикаторов.
            known_base_keys: Список известных base_key из реестра.

        Returns:
            Множество пар (base_key, value_key).
        """
        required_indicators = set()

        for full_key in full_keys:
            # OHLCV колонки не являются индикаторами - пропускаем
            if full_key in OHLCV_COLUMNS:
                continue

            # Ищем подходящий base_key в реестре
            parsed = False
            for base_key in known_base_keys:
                if full_key.startswith(base_key + "_"):
                    value_key = full_key[len(base_key) + 1 :]
                    required_indicators.add((base_key, value_key))
                    parsed = True
                    break

            if not parsed:
                logger.warning(
                    "strategy_analyzer.full_key_parse_failed",
                    full_key=full_key,
                    known_base_keys_sample=known_base_keys[:10],
                )

        # Фильтруем OHLCV
        filtered_out_count = len([k for k in full_keys if k in OHLCV_COLUMNS])
        if filtered_out_count > 0:
            logger.debug(
                "strategy_analyzer.filtered_out_ohlcv",
                filtered_out_count=filtered_out_count,
            )

        return required_indicators
