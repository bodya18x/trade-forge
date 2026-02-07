"""
Модуль для расчета lookback периода индикаторов.

Используется для проверки достаточности исторических данных перед запуском бэктеста.
Логика основана на реализации индикаторов в Data Processor.
"""

from __future__ import annotations

from typing import Any

from tradeforge_logger import get_logger

log = get_logger(__name__)


# Маппинг индикаторов на функции расчета lookback
# Логика взята из services/analytics/data_processor/calc/
INDICATOR_LOOKBACK_CALCULATORS = {
    # TALib индикаторы (из talib_indicators.py)
    "rsi": lambda params: params.get("timeperiod", 14) * 2,
    "macd": lambda params: (
        params.get("slowperiod", 26) + params.get("signalperiod", 9)
    )
    * 2,
    "sma": lambda params: params.get("timeperiod", 20) * 2,
    "ema": lambda params: params.get("timeperiod", 20) * 2,
    "bbands": lambda params: params.get("timeperiod", 20) * 2,
    "adx": lambda params: params.get("timeperiod", 14) * 2,
    "atr": lambda params: params.get("timeperiod", 14) * 2,
    "stoch": lambda params: (
        params.get("fastk_period", 14)
        + params.get("slowk_period", 3)
        + params.get("slowd_period", 3)
    )
    * 2,
    "mfi": lambda params: params.get("timeperiod", 14) * 2,
    # Pandas-TA индикаторы (из pandas_ta_indicators.py)
    "supertrend": lambda params: params.get("length", 10) * 2,
    "tsi": lambda params: (params.get("slow", 25) + params.get("signal", 13))
    * 2,
    "squeeze": lambda params: 20
    * 2,  # Фиксированный lookback для Squeeze (использует BB и Keltner с периодом 20)
    "vortex": lambda params: params.get("length", 14) * 2,
    "ichimoku": lambda params: params.get("senkou", 52) * 2,
}

# Fallback lookback для неизвестных индикаторов (консервативная оценка)
DEFAULT_LOOKBACK = 100


def calculate_indicator_lookback(
    indicator_name: str, params: dict[str, Any]
) -> int:
    """
    Рассчитывает lookback период для конкретного индикатора.

    Args:
        indicator_name: Название индикатора (например, 'ema', 'rsi')
        params: Параметры индикатора (например, {'timeperiod': 50})

    Returns:
        Количество свечей, необходимых для прогрева индикатора
    """
    if indicator_name not in INDICATOR_LOOKBACK_CALCULATORS:
        log.warning(
            "indicator.lookback.unknown",
            indicator_name=indicator_name,
            default_lookback=DEFAULT_LOOKBACK,
        )
        return DEFAULT_LOOKBACK

    try:
        return INDICATOR_LOOKBACK_CALCULATORS[indicator_name](params)
    except Exception as e:
        log.error(
            "indicator.lookback.calculation.error",
            indicator_name=indicator_name,
            params=params,
            error=str(e),
            exc_info=True,
        )
        return DEFAULT_LOOKBACK


def calculate_max_lookback_from_definitions(
    indicator_defs: list[dict[str, Any]],
) -> int:
    """
    Рассчитывает максимальный lookback период из списка определений индикаторов.

    Args:
        indicator_defs: Список определений индикаторов из стратегии
            Формат: [{"name": "ema", "params": {"timeperiod": 50}}, ...]

    Returns:
        Максимальный lookback среди всех индикаторов
    """
    if not indicator_defs:
        return 0

    lookbacks = []
    for ind_def in indicator_defs:
        name = ind_def.get("name")
        params = ind_def.get("params", {})

        if not name:
            log.warning(
                "indicator.definition.empty",
                definition=ind_def,
            )
            continue

        lookback = calculate_indicator_lookback(name, params)
        lookbacks.append(lookback)

        log.debug(
            "indicator.lookback.calculated",
            indicator=name,
            params=params,
            lookback=lookback,
        )

    if not lookbacks:
        return 0

    max_lookback = max(lookbacks)

    log.debug(
        "indicator.lookback.max.calculated",
        indicators_count=len(indicator_defs),
        max_lookback=max_lookback,
    )

    return max_lookback


def extract_indicator_definitions_from_strategy(
    strategy_definition: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Извлекает определения индикаторов из AST стратегии.

    Рекурсивно обходит все узлы стратегии и извлекает indicator_key,
    затем парсит их в формат определений индикаторов.

    Args:
        strategy_definition: AST стратегии (поле definition из таблицы strategies)

    Returns:
        Список определений индикаторов [{"name": "ema", "params": {...}}, ...]
    """
    indicator_keys: set[str] = set()

    def dive(node: Any) -> None:
        """Рекурсивно обходит AST и собирает indicator_key."""
        if isinstance(node, dict):
            node_type = node.get("type")

            # Извлекаем ключи индикаторов из разных типов узлов
            if (
                node_type
                in [
                    "INDICATOR_VALUE",
                    "PREV_INDICATOR_VALUE",
                ]
                and "key" in node
            ):
                indicator_keys.add(node["key"])
            elif node_type == "INDICATOR_BASED":
                if node.get("buy_value_key"):
                    indicator_keys.add(node["buy_value_key"])
                if node.get("sell_value_key"):
                    indicator_keys.add(node["sell_value_key"])
            elif (
                node_type
                in [
                    "SUPER_TREND_FLIP",
                    "MACD_CROSSOVER_FLIP",
                ]
                and "indicator_key" in node
            ):
                indicator_keys.add(node["indicator_key"])

            # Рекурсивно обходим вложенные узлы
            for value in node.values():
                if isinstance(value, (dict, list)):
                    dive(value)

        elif isinstance(node, list):
            for item in node:
                dive(item)

    # Запускаем рекурсивный обход
    dive(strategy_definition)

    # Парсим indicator_key в определения
    indicator_defs = []
    for key in indicator_keys:
        ind_def = _parse_indicator_key_to_definition(key)
        if ind_def:
            indicator_defs.append(ind_def)

    log.debug(
        "indicator.extraction.completed",
        indicators_count=len(indicator_defs),
        indicators=[
            f"{ind['name']}({ind.get('params', {})})" for ind in indicator_defs
        ],
    )

    return indicator_defs


def _parse_indicator_key_to_definition(
    indicator_key: str,
) -> dict[str, Any] | None:
    """
    Парсит indicator_key в определение индикатора.

    Примеры:
        "ema_timeperiod_50_value" -> {"name": "ema", "params": {"timeperiod": 50}}
        "macd_fastperiod_12_signalperiod_9_slowperiod_26_macd" -> {"name": "macd", "params": {...}}
        "supertrend_length_10_multiplier_3.0_direction" -> {"name": "supertrend", "params": {...}}

    Args:
        indicator_key: Полный ключ индикатора

    Returns:
        Определение индикатора или None если не удалось распарсить
    """
    # Пропускаем OHLCV ключи (они не индикаторы)
    if indicator_key in ["open", "high", "low", "close", "volume"]:
        return None

    # Разбиваем ключ на части
    parts = indicator_key.split("_")

    if len(parts) < 2:
        log.warning(
            "indicator.key.parse.failed",
            indicator_key=indicator_key,
        )
        return None

    # Первая часть - имя индикатора
    indicator_name = parts[0]

    # Парсим параметры (пары ключ-значение)
    params = {}
    i = 1
    while (
        i < len(parts) - 1
    ):  # -1 чтобы пропустить последнюю часть (value_key)
        param_name = parts[i]
        param_value_str = parts[i + 1]

        # Пытаемся преобразовать в число
        try:
            # Сначала пробуем int
            param_value: int | float = int(param_value_str)
        except ValueError:
            try:
                # Если не int, пробуем float
                param_value = float(param_value_str)
            except ValueError:
                # Если не число, оставляем как строку
                param_value = param_value_str  # type: ignore

        params[param_name] = param_value
        i += 2

    return {"name": indicator_name, "params": params}
