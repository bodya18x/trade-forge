"""
Indicator Factory для создания индикаторов по определениям.

Предоставляет централизованный реестр всех доступных индикаторов
и фабричную функцию для создания pipeline.
"""

from __future__ import annotations

from typing import Any

from tradeforge_logger import get_logger

from .base import BaseIndicator, IndicatorPipeline
from .pandas_ta_indicators import (
    IchimokuIndicator,
    SqueezeMomentumIndicator,
    SuperTrendIndicator,
    TSIIndicator,
    VortexIndicator,
)
from .talib_indicators import (
    ADXIndicator,
    ATRIndicator,
    BollingerBandsIndicator,
    EMAIndicator,
    MACDIndicator,
    MFIIndicator,
    RSIIndicator,
    SMAIndicator,
    StochasticIndicator,
)

logger = get_logger(__name__)

INDICATOR_REGISTRY: dict[str, type[BaseIndicator]] = {
    "macd": MACDIndicator,
    "rsi": RSIIndicator,
    "sma": SMAIndicator,
    "ema": EMAIndicator,
    "bbands": BollingerBandsIndicator,
    "adx": ADXIndicator,
    "atr": ATRIndicator,
    "stoch": StochasticIndicator,
    "mfi": MFIIndicator,
    "tsi": TSIIndicator,
    "supertrend": SuperTrendIndicator,
    "squeeze": SqueezeMomentumIndicator,
    "vortex": VortexIndicator,
    "ichimoku": IchimokuIndicator,
}


def get_available_indicators() -> list[str]:
    """
    Возвращает список всех доступных индикаторов.

    Returns:
        Список имён зарегистрированных индикаторов.
    """
    return list(INDICATOR_REGISTRY.keys())


def create_indicator_pipeline_from_defs(
    indicator_definitions: list[dict[str, Any]]
) -> IndicatorPipeline:
    """
    Создает пайплайн индикаторов из списка определений.

    Args:
        indicator_definitions: Список определений вида:
            [{"name": "sma", "params": {"period": 20}}, ...]

    Returns:
        IndicatorPipeline с настроенными индикаторами.

    Example:
        >>> defs = [{"name": "rsi", "params": {"timeperiod": 14}}]
        >>> pipeline = create_indicator_pipeline_from_defs(defs)
        >>> len(pipeline.indicators)
        1
    """
    indicators = []

    for definition in indicator_definitions:
        name = definition.get("name")
        params = definition.get("params", {})

        if not name:
            logger.warning("factory.missing_name", definition=definition)
            continue

        indicator_class = INDICATOR_REGISTRY.get(name)

        if not indicator_class:
            logger.warning("factory.unknown_indicator", name=name)
            continue

        try:
            indicator = indicator_class(**params)
            indicators.append(indicator)

            logger.debug(
                "factory.indicator_created",
                name=name,
                params=params,
            )

        except TypeError as e:
            logger.error(
                "factory.invalid_params",
                name=name,
                params=params,
                error=str(e),
            )

    return IndicatorPipeline(indicators)
