"""Константы для Trading Engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# ============================================================================
# ТАЙМАУТЫ (в секундах)
# ============================================================================
BACKTEST_TIMEOUT_SECONDS = 600
"""Максимальное время выполнения одного бэктеста (10 минут)."""

SIMULATION_TIMEOUT_SECONDS = 300
"""Максимальное время выполнения симуляции бэктеста (5 минут)."""

CLICKHOUSE_QUERY_TIMEOUT_SECONDS = 120
"""Таймаут для запросов к ClickHouse (2 минуты)."""

# ============================================================================
# СИМУЛЯЦИЯ - МОНИТОРИНГ И ПРОГРЕСС
# ============================================================================
SIMULATION_PROGRESS_LOG_INTERVAL = 0.10
"""Интервал логирования прогресса симуляции (0.10 = каждые 10%)."""

SIMULATION_TIMEOUT_CHECK_INTERVAL = 1000
"""Интервал проверки timeout в симуляции (каждые N свечей)."""

# ============================================================================
# PERFORMANCE THRESHOLDS (для warnings)
# ============================================================================
SLOW_QUERY_THRESHOLD_MS = 5000
"""Threshold для медленных ClickHouse запросов (5 секунд)."""

SLOW_DATA_LOAD_THRESHOLD_MS = 5000
"""Threshold для медленной загрузки данных (5 секунд)."""

# ============================================================================
# ЛИМИТЫ
# ============================================================================
MAX_CANDLES_PER_BACKTEST = 100_000
"""Максимальное количество свечей для одного бэктеста."""

# ============================================================================
# МЕТРИКИ СТАБИЛЬНОСТИ
# ============================================================================
MIN_TRADES_FOR_STABILITY_SCORE = 10
"""Минимальное количество сделок для расчета stability score."""

MAX_PROFIT_FACTOR_CAP = 10.0
"""Максимальное значение profit factor для нормализации."""

MAX_DRAWDOWN_DEFAULT = 100.0
"""Значение max drawdown по умолчанию (100%)."""

MAX_PROFIT_STD_DEV_DEFAULT = 100.0
"""Значение стандартного отклонения прибыли по умолчанию."""

EPSILON = 1e-6
"""Малое число для предотвращения деления на ноль."""

CONSECUTIVE_LOSSES_PENALTY_FACTOR = 0.2
"""Коэффициент штрафа за серии убытков (exp decay)."""

TRADE_COUNT_CONFIDENCE_FACTOR = 0.05
"""Коэффициент уверенности на основе количества сделок."""

MAX_STABILITY_SCORE = 100.0
"""Максимальное значение stability score."""

# ============================================================================
# ВЕСА ДЛЯ STABILITY SCORE
# ============================================================================


@dataclass(frozen=True)
class StabilityWeights:
    """
    Веса компонентов для расчета Stability Score.

    Веса определяют важность каждого показателя при расчете общей метрики стабильности.
    Сумма всех весов должна быть равна 1.0.

    Attributes:
        win_rate: Вес win rate (процент прибыльных сделок).
        profit_factor: Вес profit factor (отношение прибылей к убыткам).
        max_drawdown: Вес max drawdown (максимальная просадка).
        avg_profit_consistency: Вес consistency прибыли (стабильность результатов).
        max_consecutive_losses: Вес максимальных последовательных убытков.

    Raises:
        ValueError: Если сумма весов не равна 1.0.
    """

    win_rate: float = 0.25
    profit_factor: float = 0.25
    max_drawdown: float = 0.20
    avg_profit_consistency: float = 0.15
    max_consecutive_losses: float = 0.15

    def __post_init__(self) -> None:
        """Валидирует что сумма весов равна 1.0."""
        total = sum(
            [
                self.win_rate,
                self.profit_factor,
                self.max_drawdown,
                self.avg_profit_consistency,
                self.max_consecutive_losses,
            ]
        )
        if not math.isclose(total, 1.0, rel_tol=1e-9):
            raise ValueError(
                f"Сумма весов Stability Score должна быть равна 1.0, получено: {total}. "
                f"Веса: win_rate={self.win_rate}, profit_factor={self.profit_factor}, "
                f"max_drawdown={self.max_drawdown}, avg_profit_consistency={self.avg_profit_consistency}, "
                f"max_consecutive_losses={self.max_consecutive_losses}"
            )


# Глобальный экземпляр с дефолтными весами
STABILITY_WEIGHTS = StabilityWeights()

# Обратная совместимость (deprecated, use STABILITY_WEIGHTS.*)
STABILITY_WEIGHT_WIN_RATE = STABILITY_WEIGHTS.win_rate
STABILITY_WEIGHT_PROFIT_FACTOR = STABILITY_WEIGHTS.profit_factor
STABILITY_WEIGHT_MAX_DRAWDOWN = STABILITY_WEIGHTS.max_drawdown
STABILITY_WEIGHT_AVG_PROFIT_CONSISTENCY = (
    STABILITY_WEIGHTS.avg_profit_consistency
)
STABILITY_WEIGHT_MAX_CONSECUTIVE_LOSSES = (
    STABILITY_WEIGHTS.max_consecutive_losses
)

# ============================================================================
# КОЛОНКИ ДАННЫХ
# ============================================================================
OHLCV_COLUMNS = {
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ticker",
    "timeframe",
    "begin",
}
"""Обязательные колонки OHLCV данных."""

CLICKHOUSE_TECHNICAL_COLUMNS = [
    "data_type",
    "indicator_key",
    "value_key",
    "value",
]
"""Технические колонки ClickHouse, которые нужно удалять при подготовке DataFrame."""

# ============================================================================
# CLICKHOUSE DUMMY VALUES
# ============================================================================
CLICKHOUSE_DUMMY_INDICATOR_KEY = "__dummy_base_key__"
"""Dummy indicator_key для ClickHouse запросов когда индикаторы не требуются."""

CLICKHOUSE_DUMMY_VALUE_KEY = "__dummy_value_key__"
"""Dummy value_key для ClickHouse запросов когда индикаторы не требуются."""

CLICKHOUSE_DUMMY_INDICATOR_PAIR = (
    CLICKHOUSE_DUMMY_INDICATOR_KEY,
    CLICKHOUSE_DUMMY_VALUE_KEY,
)
"""Dummy пара (indicator_key, value_key) для ClickHouse запросов."""

# ============================================================================
# ENUM КЛАССЫ (Использовать везде вместо строковых констант)
# ============================================================================


class ExitReason(str, Enum):
    """
    Причины закрытия позиции.

    Наследуется от str для совместимости с JSON, БД и строковыми операциями.
    """

    STOP_LOSS = "Stop Loss"
    TAKE_PROFIT = "Take Profit"
    EXIT_SIGNAL = "Exit Signal"
    END_OF_DATA = "End of Data"
    FLIP = "Position Flip"


class PositionType(str, Enum):
    """
    Типы торговых позиций.

    Наследуется от str для совместимости с JSON, БД и строковыми операциями.
    """

    BUY = "BUY"
    SELL = "SELL"


class JobStatus(str, Enum):
    """
    Статусы задач на бэктестинг.

    Наследуется от str для совместимости с JSON, БД и строковыми операциями.
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
