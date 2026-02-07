import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import TimestampTemplate


class JobStatus(enum.Enum):
    PENDING = "PENDING"
    CALCULATING = "CALCULATING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BatchStatus(enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIALLY_FAILED = "PARTIALLY_FAILED"


class BacktestJobs(TimestampTemplate):
    """Задачи на выполнение бэктестов."""

    __tablename__ = "backtest_jobs"
    __table_args__ = (
        # Индекс для эффективной сортировки бэктестов пользователя
        Index(
            "idx_backtest_jobs_user_sorting",
            "user_id",
            "created_at",
            "status",
        ),
        # Индекс для фильтрации по стратегии
        Index(
            "idx_backtest_jobs_strategy",
            "strategy_id",
            "created_at",
        ),
        # Индекс для связи с batch
        Index(
            "idx_backtest_jobs_batch",
            "batch_id",
            "created_at",
        ),
        {"schema": "trader_core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trader_core.strategies.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth.users.id", ondelete="CASCADE")
    )
    ticker: Mapped[str] = mapped_column(String(50))
    timeframe: Mapped[str] = mapped_column(String(10))
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status_enum",
            create_type=True,
            schema="trader_core",
        ),
        default=JobStatus.PENDING,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    # Снапшот стратегии на момент создания бэктеста
    strategy_definition_snapshot: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Снапшот определения стратегии на момент создания бэктеста",
        comment="Снапшот AST стратегии",
    )

    # Параметры симуляции
    simulation_params: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Параметры симуляции бэктеста (комиссии, начальный капитал и т.д.)",
        comment="Параметры симуляции",
    )

    # Связь с batch (если это часть группового запуска)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("trader_core.backtest_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Флаг учета в лимитах пользователя
    counts_towards_limit: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Учитывается ли задача в лимитах пользователя (False для failed pre-validation)",
        comment="Флаг учета в лимитах",
    )


class BacktestBatches(TimestampTemplate):
    """Групповые задачи на выполнение бэктестов."""

    __tablename__ = "backtest_batches"
    __table_args__ = (
        # Индекс для эффективной сортировки batches пользователя
        Index(
            "idx_backtest_batches_user_sorting",
            "user_id",
            "created_at",
            "status",
        ),
        {"schema": "trader_core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth.users.id", ondelete="CASCADE")
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BatchStatus] = mapped_column(
        Enum(
            BatchStatus,
            name="batch_status_enum",
            create_type=True,
            schema="trader_core",
        ),
        default=BatchStatus.PENDING,
        index=True,
    )
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_completion_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
