"""
Унифицированные Pydantic схемы для работы с бэктестами.

Содержит все схемы для создания, управления и получения результатов бэктестов.
Решает проблему дублирования между Gateway и Internal API.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# === ПЕРЕЧИСЛЕНИЯ ===


class JobStatusEnum(str, enum.Enum):
    """Статусы задачи на бэктест, синхронизированные с БД."""

    PENDING = "PENDING"
    CALCULATING = "CALCULATING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# === ПАРАМЕТРЫ СИМУЛЯЦИИ ===


class SimulationParameters(BaseModel):
    """
    Унифицированные параметры симуляции торговли.

    РЕШЕНИЕ: Используем формат из Gateway (более подробный и понятный).
    """

    initial_balance: float = Field(
        default=100000.0, gt=0, description="Начальный баланс для симуляции"
    )
    commission_pct: float = Field(
        default=0.04,
        ge=0,
        le=10,
        description="Комиссия в процентах (0.04 означает 0.04%)",
    )
    position_size_pct: float = Field(
        default=100.0,
        gt=0,
        le=500,
        description="Размер позиции в % от доступного капитала (>100% = использование плеча, макс 5x)",
    )


# === ЗАПРОСЫ НА СОЗДАНИЕ ===


class BacktestCreateRequest(BaseModel):
    """
    Унифицированный запрос на создание нового бэктеста.

    Объединяет лучшие практики из обоих API:
    - Валидацию из Gateway
    - Простоту типов из Internal
    """

    strategy_id: uuid.UUID = Field(..., description="ID тестируемой стратегии")
    ticker: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Торговый инструмент (например, SBER)",
    )
    timeframe: str = Field(
        ...,
        pattern=r"^(1d|10min|1h|1w|1m)$",
        description="Таймфрейм для тестирования (актуальные: 1d, 10min, 1h, 1w, 1m)",
    )
    start_date: str = Field(
        ...,
        description="Дата начала тестирования в ISO формате (YYYY-MM-DD или с временем)",
    )
    end_date: str = Field(
        ...,
        description="Дата окончания тестирования в ISO формате (YYYY-MM-DD или с временем)",
    )
    simulation_params: SimulationParameters = Field(
        default_factory=SimulationParameters,
        description="Параметры симуляции торговли",
    )


# === РЕЗУЛЬТАТЫ И МЕТРИКИ ===


class TradeDetails(BaseModel):
    """Детали отдельной сделки в бэктесте."""

    entry_time: datetime = Field(..., description="Время входа в позицию")
    exit_time: datetime = Field(..., description="Время выхода из позиции")
    side: str = Field(..., description="Направление сделки (BUY/SELL)")
    entry_price: Decimal = Field(..., description="Цена входа", ge=0)
    exit_price: Decimal = Field(..., description="Цена выхода", ge=0)
    quantity: Decimal = Field(..., description="Количество инструмента", ge=0)
    pnl: Decimal = Field(..., description="Прибыль/убыток по сделке")
    pnl_percentage: Decimal = Field(..., description="P&L в процентах")
    exit_reason: str = Field(..., description="Причина закрытия позиции")
    commission: Decimal = Field(..., description="Комиссия по сделке", ge=0)


class BacktestMetrics(BaseModel):
    """
    Унифицированные агрегированные метрики бэктеста.

    Содержит как базовые, так и расширенные метрики для детального анализа.
    """

    # Базовые метрики (обязательные)
    net_total_profit_pct: float = Field(
        ..., description="Общая доходность в % с учетом комиссий"
    )
    win_rate: float = Field(
        ..., description="Процент выигрышных сделок", ge=0, le=100
    )
    max_drawdown_pct: float = Field(
        ..., description="Максимальная просадка в процентах", ge=0
    )
    total_trades: int = Field(..., description="Общее количество сделок", ge=0)

    # Расширенные метрики (опциональные)
    initial_balance: float | None = Field(None, description="Начальный баланс")
    net_final_balance: float | None = Field(
        None, description="Конечный баланс с учетом комиссий"
    )
    wins: int | None = Field(None, description="Количество выигрышных сделок")
    losses: int | None = Field(None, description="Количество убыточных сделок")
    profit_factor: float | None = Field(None, description="Фактор прибыли")
    sharpe_ratio: float | None = Field(None, description="Коэффициент Шарпа")
    stability_score: float | None = Field(
        None, description="Оценка стабильности"
    )
    avg_net_profit_pct: float | None = Field(
        None, description="Средняя прибыль с сделки в %"
    )
    net_profit_std_dev: float | None = Field(
        None, description="Стандартное отклонение прибыли"
    )
    avg_win_pct: float | None = Field(
        None, description="Средняя прибыльная сделка в %"
    )
    avg_loss_pct: float | None = Field(
        None, description="Средняя убыточная сделка в %"
    )
    max_consecutive_wins: int | None = Field(
        None, description="Максимум выигрышей подряд"
    )
    max_consecutive_losses: int | None = Field(
        None, description="Максимум убытков подряд"
    )


class BacktestResults(BaseModel):
    """
    Полные результаты выполненного бэктеста.

    Объединяет метрики и детальный список сделок.
    """

    metrics: BacktestMetrics = Field(..., description="Агрегированные метрики")
    trades: list[dict] = Field(
        ..., description="Список всех сделок (пока как dict для совместимости)"
    )

    model_config = ConfigDict(from_attributes=True)


# === ИНФОРМАЦИЯ О ЗАДАЧЕ ===


class BacktestJobInfo(BaseModel):
    """Информация о задаче на бэктест."""

    id: uuid.UUID = Field(..., description="Уникальный идентификатор задачи")
    strategy_id: uuid.UUID = Field(..., description="ID тестируемой стратегии")
    user_id: uuid.UUID = Field(..., description="ID пользователя")
    ticker: str = Field(..., description="Торговый инструмент")
    timeframe: str = Field(..., description="Таймфрейм")
    start_date: datetime = Field(..., description="Дата начала тестирования")
    end_date: datetime = Field(..., description="Дата окончания тестирования")
    simulation_params: SimulationParameters = Field(
        ..., description="Параметры симуляции"
    )
    status: JobStatusEnum = Field(..., description="Текущий статус задачи")
    error_message: str | None = Field(
        None, description="Сообщение об ошибке, если статус FAILED"
    )
    created_at: datetime = Field(..., description="Время создания задачи")
    updated_at: datetime = Field(
        ..., description="Время последнего обновления"
    )

    # Дополнительные поля для Internal API
    strategy_definition_snapshot: dict | None = Field(
        None, description="Снимок определения стратегии на момент создания"
    )

    model_config = ConfigDict(from_attributes=True)


# === ПОЛНЫЕ ОТВЕТЫ ===


class BacktestFullResponse(BaseModel):
    """
    УНИФИЦИРОВАННЫЙ полный ответ по бэктесту.

    РЕШЕНИЕ КОНФЛИКТА: Используем 'results' (как в Gateway),
    но структуру данных как в Internal API.
    """

    job: BacktestJobInfo = Field(..., description="Информация о задаче")
    results: BacktestResults | None = Field(
        None,
        description="Результаты бэктеста (присутствуют только при статусе COMPLETED)",
    )


# === КРАТКИЕ ОТВЕТЫ ДЛЯ СПИСКОВ ===


class BacktestSummary(BaseModel):
    """Краткая информация о бэктесте для списков."""

    id: uuid.UUID = Field(..., description="ID задачи")
    strategy_id: uuid.UUID = Field(..., description="ID стратегии")
    ticker: str = Field(..., description="Торговый инструмент")
    timeframe: str = Field(..., description="Таймфрейм")
    start_date: datetime = Field(..., description="Дата начала")
    end_date: datetime = Field(..., description="Дата окончания")
    status: JobStatusEnum = Field(..., description="Статус задачи")

    # Базовые метрики (если доступны)
    net_total_profit_pct: float | None = Field(
        None, description="Общая доходность в % с учетом комиссий"
    )
    total_trades: int | None = Field(
        None, description="Общее количество сделок"
    )
    win_rate: float | None = Field(
        None, description="Процент выигрышных сделок"
    )
    max_drawdown_pct: float | None = Field(
        None, description="Максимальная просадка в процентах"
    )

    # Расширенные метрики (если доступны)
    initial_balance: float | None = Field(None, description="Начальный баланс")
    net_final_balance: float | None = Field(
        None, description="Конечный баланс с учетом комиссий"
    )
    wins: int | None = Field(None, description="Количество выигрышных сделок")
    losses: int | None = Field(None, description="Количество убыточных сделок")
    profit_factor: float | None = Field(None, description="Фактор прибыли")
    sharpe_ratio: float | None = Field(None, description="Коэффициент Шарпа")
    stability_score: float | None = Field(
        None, description="Оценка стабильности"
    )
    avg_net_profit_pct: float | None = Field(
        None, description="Средняя прибыль с сделки в %"
    )
    net_profit_std_dev: float | None = Field(
        None, description="Стандартное отклонение прибыли"
    )
    avg_win_pct: float | None = Field(
        None, description="Средняя прибыльная сделка в %"
    )
    avg_loss_pct: float | None = Field(
        None, description="Средняя убыточная сделка в %"
    )
    max_consecutive_wins: int | None = Field(
        None, description="Максимум выигрышей подряд"
    )
    max_consecutive_losses: int | None = Field(
        None, description="Максимум убытков подряд"
    )

    created_at: datetime = Field(..., description="Время создания")

    model_config = ConfigDict(from_attributes=True)


class BacktestSortBy(str, enum.Enum):
    """Доступные поля для сортировки бэктестов."""

    CREATED_AT = "created_at"
    NET_TOTAL_PROFIT_PCT = "net_total_profit_pct"
    TOTAL_TRADES = "total_trades"
    WIN_RATE = "win_rate"
    MAX_DRAWDOWN_PCT = "max_drawdown_pct"
    PROFIT_FACTOR = "profit_factor"
    SHARPE_RATIO = "sharpe_ratio"
    # Расширенные метрики
    WINS = "wins"
    LOSSES = "losses"
    STABILITY_SCORE = "stability_score"
    AVG_NET_PROFIT_PCT = "avg_net_profit_pct"
    NET_PROFIT_STD_DEV = "net_profit_std_dev"
    AVG_WIN_PCT = "avg_win_pct"
    AVG_LOSS_PCT = "avg_loss_pct"
    MAX_CONSECUTIVE_WINS = "max_consecutive_wins"
    MAX_CONSECUTIVE_LOSSES = "max_consecutive_losses"
    INITIAL_BALANCE = "initial_balance"
    NET_FINAL_BALANCE = "net_final_balance"
