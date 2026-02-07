"""
Helper функции для CRUD операций.

Содержит переиспользуемые функции для общих паттернов в CRUD операциях.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.engine import Row
from sqlalchemy.sql.elements import BinaryExpression, UnaryExpression
from tradeforge_db import BacktestJobs, BacktestResults, Strategies


def filter_active_strategies():
    """
    Создает фильтр для исключения удаленных стратегий.

    Используется в JOIN запросах для фильтрации стратегий с is_deleted=False.

    Returns:
        SQLAlchemy условие для WHERE клаузы
    """
    return or_(Strategies.id.is_(None), ~Strategies.is_deleted)


def row_to_dict(row: Row, model_instance: Any = None) -> dict[str, Any]:
    """
    Конвертирует SQLAlchemy Row в словарь.

    Args:
        row: SQLAlchemy Row объект
        model_instance: Any - опциональный экземпляр модели (первый элемент row)

    Returns:
        Словарь с данными из Row

    Example:
        >>> row = result.one()
        >>> data = row_to_dict(row, row[0])
    """
    if model_instance is not None:
        # Если передан model instance, используем его атрибуты
        result = {}
        for key, value in model_instance.__dict__.items():
            if not key.startswith("_"):
                result[key] = value

        # Добавляем остальные поля из row через _mapping
        row_dict = row._mapping
        for key, value in row_dict.items():
            if key not in result and not hasattr(model_instance, key):
                result[key] = value

        return result
    else:
        # Простая конвертация через _mapping
        return dict(row._mapping)


def safe_int(value: Any) -> int | None:
    """
    Безопасно конвертирует значение в int.

    Args:
        value: Any - принимает любые типы для конвертации (str, int, float, etc.)

    Returns:
        int или None если значение пустое
    """
    if value is None:
        return None
    return int(value)


def model_to_dict(
    instance: Any, exclude_private: bool = True
) -> dict[str, Any]:
    """
    Конвертирует SQLAlchemy модель в словарь.

    Args:
        instance: Any - принимает любый SQLAlchemy модель для гибкости
        exclude_private: Исключать ли приватные атрибуты (начинающиеся с _)

    Returns:
        Словарь с атрибутами модели
    """
    if exclude_private:
        return {
            k: v for k, v in instance.__dict__.items() if not k.startswith("_")
        }
    return dict(instance.__dict__)


# Маппинг полей сортировки бэктестов на SQLAlchemy выражения
BACKTEST_SORT_FIELDS = {
    "created_at": BacktestJobs.created_at,
    "net_total_profit_pct": BacktestResults.metrics[
        "net_total_profit_pct"
    ].as_float(),
    "total_trades": BacktestResults.metrics["total_trades"].as_float(),
    "win_rate": BacktestResults.metrics["win_rate"].as_float(),
    "max_drawdown_pct": BacktestResults.metrics["max_drawdown_pct"].as_float(),
    "profit_factor": BacktestResults.metrics["profit_factor"].as_float(),
    "sharpe_ratio": BacktestResults.metrics["sharpe_ratio"].as_float(),
    "wins": BacktestResults.metrics["wins"].as_float(),
    "losses": BacktestResults.metrics["losses"].as_float(),
    "stability_score": BacktestResults.metrics["stability_score"].as_float(),
    "avg_net_profit_pct": BacktestResults.metrics[
        "avg_net_profit_pct"
    ].as_float(),
    "net_profit_std_dev": BacktestResults.metrics[
        "net_profit_std_dev"
    ].as_float(),
    "avg_win_pct": BacktestResults.metrics["avg_win_pct"].as_float(),
    "avg_loss_pct": BacktestResults.metrics["avg_loss_pct"].as_float(),
    "max_consecutive_wins": BacktestResults.metrics[
        "max_consecutive_wins"
    ].as_float(),
    "max_consecutive_losses": BacktestResults.metrics[
        "max_consecutive_losses"
    ].as_float(),
    "initial_balance": BacktestResults.metrics["initial_balance"].as_float(),
    "net_final_balance": BacktestResults.metrics[
        "net_final_balance"
    ].as_float(),
}


def get_backtest_sort_clauses(
    sort_by: str,
    sort_direction: str = "desc",
    fallback_field: UnaryExpression | BinaryExpression | None = None,
) -> list[UnaryExpression]:
    """
    Возвращает список SQLAlchemy выражений для ORDER BY в запросах бэктестов.

    Args:
        sort_by: Название поля для сортировки (ключ из BACKTEST_SORT_FIELDS)
        sort_direction: Направление сортировки ("asc" или "desc")
        fallback_field: Поле для вторичной сортировки (UnaryExpression | BinaryExpression)
                       По умолчанию BacktestJobs.created_at

    Returns:
        Список SQLAlchemy UnaryExpression для ORDER BY

    Example:
        >>> clauses = get_backtest_sort_clauses("win_rate", "desc")
        >>> stmt = stmt.order_by(*clauses)
    """
    if fallback_field is None:
        fallback_field = BacktestJobs.created_at

    # Получаем поле из маппинга или используем fallback
    order_field = BACKTEST_SORT_FIELDS.get(sort_by, fallback_field)

    # Применяем направление сортировки
    if sort_direction.lower() == "asc":
        clauses = [order_field.asc().nullslast()]
    else:
        clauses = [order_field.desc().nullslast()]

    # Добавляем fallback сортировку для стабильности результатов
    if sort_by != "created_at":
        clauses.append(fallback_field.desc())

    return clauses
