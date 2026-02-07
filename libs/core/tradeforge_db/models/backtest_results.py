import uuid

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampTemplate


class BacktestResults(TimestampTemplate):
    """Хранит итоговые метрики и детали сделок каждого выполненного бэктеста."""

    __tablename__ = "backtest_results"
    __table_args__ = (
        # GIN индекс для быстрого поиска по JSONB полям
        Index(
            "idx_backtest_results_metrics_gin",
            "metrics",
            postgresql_using="gin",
        ),
        # Функциональные индексы для популярных метрик (для сортировки)
        Index(
            "idx_backtest_results_roi",
            text(
                "COALESCE((metrics->>'roi')::numeric, (metrics->>'net_total_profit_pct')::numeric)"
            ),
            postgresql_where=text(
                "metrics ? 'roi' OR metrics ? 'net_total_profit_pct'"
            ),
        ),
        Index(
            "idx_backtest_results_total_trades",
            text("(metrics->>'total_trades')::integer"),
            postgresql_where=text("metrics ? 'total_trades'"),
        ),
        Index(
            "idx_backtest_results_win_rate",
            text("(metrics->>'win_rate')::numeric"),
            postgresql_where=text("metrics ? 'win_rate'"),
        ),
        Index(
            "idx_backtest_results_max_drawdown",
            text("(metrics->>'max_drawdown_pct')::numeric"),
            postgresql_where=text("metrics ? 'max_drawdown_pct'"),
        ),
        Index(
            "idx_backtest_results_profit_factor",
            text("(metrics->>'profit_factor')::numeric"),
            postgresql_where=text("metrics ? 'profit_factor'"),
        ),
        Index(
            "idx_backtest_results_sharpe_ratio",
            text("(metrics->>'sharpe_ratio')::numeric"),
            postgresql_where=text("metrics ? 'sharpe_ratio'"),
        ),
        {"schema": "trader_core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Уникальный идентификатор результата бэктеста",
        comment="UUID результата бэктеста",
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "trader_core.backtest_jobs.id",
        ),
        doc="Внешний ключ на таблицу `backtest_jobs`",
        comment="FK на trader_core.backtest_jobs",
    )

    metrics: Mapped[dict] = mapped_column(
        JSONB,
        doc="Итоговые метрики бэктеста в формате JSONB",
        comment="JSONB с метриками (ROI, WinRate, MaxDrawdown и т.д.)",
    )

    trades: Mapped[list[dict]] = mapped_column(
        JSONB,
        doc="Список всех симулированных сделок в формате JSONB",
        comment="JSONB-массив сделок (entry, exit, profit и т.д.)",
    )
