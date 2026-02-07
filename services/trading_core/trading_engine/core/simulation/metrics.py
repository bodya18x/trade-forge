from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List

from tradeforge_logger import get_logger

from core.common import (
    CONSECUTIVE_LOSSES_PENALTY_FACTOR,
    EPSILON,
    MAX_DRAWDOWN_DEFAULT,
    MAX_PROFIT_FACTOR_CAP,
    MAX_PROFIT_STD_DEV_DEFAULT,
    MAX_STABILITY_SCORE,
    MIN_TRADES_FOR_STABILITY_SCORE,
    STABILITY_WEIGHTS,
    TRADE_COUNT_CONFIDENCE_FACTOR,
)
from models.backtest import BacktestConfig, BacktestTrade

logger = get_logger(__name__)


def calculate_metrics(
    trades: List[BacktestTrade], config: BacktestConfig
) -> Dict[str, Any]:
    """
    Рассчитывает полный набор метрик эффективности на основе списка сделок и конфигурации бэктеста.

    Args:
        trades (List[BacktestTrade]): Список завершенных сделок.
        config (BacktestConfig): Конфигурация бэктеста.

    Returns:
        Dict[str, Any]: Словарь с рассчитанными метриками.
    """
    if not trades:
        logger.info(
            "metrics.no_trades_found",
            message="No trades to calculate metrics, returning empty result",
            initial_balance=config.initial_balance,
        )
        return _get_empty_metrics_dict(config.initial_balance)

    # --- Инициализация переменных ---
    net_equity_curve = [config.initial_balance]
    gross_equity_curve = [config.initial_balance]

    gross_profit_pct_list = []
    net_profit_pct_list = []

    wins = 0  # Считаем по чистой прибыли
    consecutive_wins = 0
    consecutive_losses = 0
    max_consecutive_wins = 0
    max_consecutive_losses = 0

    # --- Основной цикл: Построение кривых эквити и сбор статистики ---
    for trade in trades:
        # Используем данные, уже рассчитанные в BacktestTrade
        gross_profit_abs = trade.gross_profit_abs
        net_profit_abs = trade.net_profit_abs

        # Рассчитываем процент от капитала на момент входа
        # (trade.entry_capital уже содержит правильное значение капитала)
        gross_profit_pct_on_capital = trade.gross_profit_pct_on_capital
        net_profit_pct_on_capital = trade.net_profit_pct_on_capital

        gross_profit_pct_list.append(gross_profit_pct_on_capital)
        net_profit_pct_list.append(net_profit_pct_on_capital)

        # Обновляем кривые эквити
        gross_equity_curve.append(gross_equity_curve[-1] + gross_profit_abs)
        net_equity_curve.append(trade.exit_capital)

        # --- Статистика по чистым результатам ---
        if net_profit_abs > 0:
            wins += 1
            consecutive_wins += 1
            consecutive_losses = 0
        else:
            consecutive_losses += 1
            consecutive_wins = 0

        max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
        max_consecutive_losses = max(
            max_consecutive_losses, consecutive_losses
        )

    # --- Финальные расчеты метрик ---
    final_gross_balance = gross_equity_curve[-1]
    final_net_balance = net_equity_curve[-1]
    total_trades = len(trades)

    gross_total_profit_pct = (
        final_gross_balance / config.initial_balance - 1
    ) * 100
    net_total_profit_pct = (
        final_net_balance / config.initial_balance - 1
    ) * 100

    # Метрики, основанные на ЧИСТЫХ результатах
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0

    net_wins_pct = [p for p in net_profit_pct_list if p > 0]
    net_losses_pct = [p for p in net_profit_pct_list if p <= 0]

    sum_net_wins_pct = sum(net_wins_pct)
    sum_net_losses_pct = sum(net_losses_pct)

    profit_factor = (
        abs(sum_net_wins_pct / sum_net_losses_pct)
        if sum_net_losses_pct != 0
        else None
    )
    max_drawdown_pct = _calculate_max_drawdown(net_equity_curve)

    avg_net_profit_pct = (
        statistics.mean(net_profit_pct_list) if net_profit_pct_list else 0.0
    )
    net_profit_std_dev = (
        statistics.stdev(net_profit_pct_list)
        if len(net_profit_pct_list) > 1
        else 0.0
    )
    sharpe_ratio = (
        (avg_net_profit_pct / net_profit_std_dev)
        if net_profit_std_dev > 0
        else None
    )

    stability_metrics = {
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "avg_profit_pct": avg_net_profit_pct,
        "profit_std_dev": net_profit_std_dev,
        "max_consecutive_losses": max_consecutive_losses,
        "total_trades": total_trades,
    }
    stability_score = _calculate_stability_score(stability_metrics)

    return {
        "initial_balance": config.initial_balance,
        # Результаты БЕЗ комиссии (Gross)
        "gross_final_balance": final_gross_balance,
        "gross_total_profit_pct": gross_total_profit_pct,
        # Результаты С комиссией (Net) - основные метрики
        "net_final_balance": final_net_balance,
        "net_total_profit_pct": net_total_profit_pct,
        # Общая статистика
        "total_trades": total_trades,
        "wins": wins,
        "losses": total_trades - wins,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe_ratio": sharpe_ratio,
        "stability_score": stability_score,
        # Дополнительная детализация
        "avg_net_profit_pct": avg_net_profit_pct,
        "net_profit_std_dev": net_profit_std_dev,
        "avg_win_pct": statistics.mean(net_wins_pct) if net_wins_pct else 0.0,
        "avg_loss_pct": (
            statistics.mean(net_losses_pct) if net_losses_pct else 0.0
        ),
        "max_consecutive_wins": max_consecutive_wins,
        "max_consecutive_losses": max_consecutive_losses,
    }


def _calculate_max_drawdown(equity_curve: List[float]) -> float:
    """Рассчитывает максимальную просадку в процентах по кривой эквити."""
    if len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    max_drawdown = 0.0

    for equity in equity_curve:
        if equity > peak:
            peak = equity

        if peak > 0:
            drawdown = (peak - equity) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    return max_drawdown * 100.0


def _calculate_stability_score(metrics: Dict[str, Any]) -> float:
    """
    Рассчитывает комплексную метрику стабильности стратегии (0-100).

    Formula:
        score = Σ(weight_i × normalized_metric_i) × trade_confidence × 100

    Components (weights):
        - Win Rate (25%): Процент прибыльных сделок
        - Profit Factor (25%): Отношение прибылей к убыткам
        - Max Drawdown (20%): Инвертированная просадка
        - Consistency (15%): Стабильность результатов (std dev)
        - Max Losses (15%): Серии убытков (exp penalty)

    Trade confidence: 1 - exp(-0.05 × total_trades)

    Returns:
        Оценка стабильности от 0 (нестабильно) до 100 (очень стабильно).
    """
    if metrics.get("total_trades", 0) < MIN_TRADES_FOR_STABILITY_SCORE:
        return 0.0

    win_rate = metrics.get("win_rate", 0.0)
    profit_factor = min(
        metrics.get("profit_factor", 0.0), MAX_PROFIT_FACTOR_CAP
    )
    max_drawdown = metrics.get("max_drawdown_pct", MAX_DRAWDOWN_DEFAULT)
    avg_profit = metrics.get("avg_profit_pct", 0.0)
    profit_std_dev = metrics.get("profit_std_dev", MAX_PROFIT_STD_DEV_DEFAULT)
    max_cons_losses = metrics.get("max_consecutive_losses", 0)
    total_trades = metrics.get("total_trades", 0)

    # Нормализация компонентов (приведение к шкале ~0-1)
    norm_win_rate = win_rate / MAX_STABILITY_SCORE
    norm_profit_factor = 1 - (
        1 / (1 + profit_factor)
    )  # от 0 до 1, асимптотически
    norm_max_drawdown = 1 - (max_drawdown / MAX_STABILITY_SCORE)
    norm_avg_profit_consistency = (
        1 - (profit_std_dev / (abs(avg_profit) + EPSILON))
        if avg_profit != 0
        else 0
    )
    norm_avg_profit_consistency = max(0, min(1, norm_avg_profit_consistency))
    norm_max_cons_losses = math.exp(
        -CONSECUTIVE_LOSSES_PENALTY_FACTOR * max_cons_losses
    )

    # Веса компонентов (из StabilityWeights dataclass)
    score = (
        norm_win_rate * STABILITY_WEIGHTS.win_rate
        + norm_profit_factor * STABILITY_WEIGHTS.profit_factor
        + norm_max_drawdown * STABILITY_WEIGHTS.max_drawdown
        + norm_avg_profit_consistency
        * STABILITY_WEIGHTS.avg_profit_consistency
        + norm_max_cons_losses * STABILITY_WEIGHTS.max_consecutive_losses
    )

    # Штраф за малое количество сделок
    trade_confidence = 1 - math.exp(
        -TRADE_COUNT_CONFIDENCE_FACTOR * total_trades
    )

    final_score = score * trade_confidence * MAX_STABILITY_SCORE

    return max(0, min(MAX_STABILITY_SCORE, final_score))


def _get_empty_metrics_dict(initial_balance: float) -> Dict[str, Any]:
    """
    Возвращает словарь с нулевыми метриками для случая, когда не было сделок.

    Структура полностью соответствует результату calculate_metrics() при отсутствии сделок.
    """
    return {
        "initial_balance": initial_balance,
        # Результаты БЕЗ комиссии (Gross) - нет сделок, баланс не изменился
        "gross_final_balance": initial_balance,
        "gross_total_profit_pct": 0.0,
        # Результаты С комиссией (Net) - основные метрики
        "net_final_balance": initial_balance,
        "net_total_profit_pct": 0.0,
        # Общая статистика
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "stability_score": 0.0,
        # Дополнительная детализация
        "avg_net_profit_pct": 0.0,
        "net_profit_std_dev": 0.0,
        "avg_win_pct": 0.0,
        "avg_loss_pct": 0.0,
        "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
        "avg_duration_hours": 0.0,
    }
