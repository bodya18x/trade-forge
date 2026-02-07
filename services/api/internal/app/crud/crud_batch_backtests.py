"""
CRUD операции для групповых бэктестов.

Этот модуль содержит функции для создания и управления групповыми задачами бэктестинга,
позволяющими пользователям запускать несколько бэктестов одновременно.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import case, cast, func, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import BacktestBatches, BacktestJobs, BatchStatus, JobStatus
from tradeforge_logger import get_logger
from tradeforge_schemas import BatchBacktestJobInfo, BatchBacktestSummary

from app.types import BatchID, UserID

log = get_logger(__name__)


async def create_batch_backtest(
    db: AsyncSession,
    *,
    user_id: UserID,
    description: str,
    total_count: int,
    estimated_completion_time: datetime | None = None,
) -> BacktestBatches:
    """
    Создает новую запись группового бэктеста.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя
        description: Описание группы
        total_count: Общее количество задач в группе
        estimated_completion_time: Оценка времени завершения

    Returns:
        Созданный объект BacktestBatches
    """
    batch = BacktestBatches(
        id=uuid.uuid4(),
        user_id=user_id,
        description=description,
        status=BatchStatus.PENDING,
        total_count=total_count,
        completed_count=0,
        failed_count=0,
        estimated_completion_time=estimated_completion_time,
    )

    db.add(batch)
    await db.flush()

    log.info(
        "batch.backtest.saved",
        batch_id=str(batch.id),
        user_id=str(user_id),
        description=description,
        total_count=total_count,
    )

    return batch


async def get_batch_by_id(
    db: AsyncSession, *, batch_id: BatchID, user_id: UserID
) -> BacktestBatches:
    """
    Получает групповой бэктест по ID для конкретного пользователя.

    Args:
        db: Асинхронная сессия базы данных
        batch_id: UUID группового бэктеста
        user_id: UUID пользователя (для проверки доступа)

    Returns:
        Объект BacktestBatches или None, если не найден или доступ запрещен
    """
    stmt = select(BacktestBatches).where(
        BacktestBatches.id == batch_id, BacktestBatches.user_id == user_id
    )

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_batch_individual_jobs(
    db: AsyncSession, *, batch_id: BatchID
) -> list[BatchBacktestJobInfo]:
    """
    Получает все индивидуальные задачи в составе группового бэктеста.

    Args:
        db: Асинхронная сессия базы данных
        batch_id: UUID группового бэктеста

    Returns:
        Список Pydantic моделей BatchBacktestJobInfo с данными индивидуальных задач
    """
    # Создаем CASE выражение для completion_time
    completion_time_expr = case(
        (
            BacktestJobs.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]),
            BacktestJobs.updated_at,
        ),
        else_=None,
    ).label("completion_time")

    stmt = (
        select(
            BacktestJobs.id.label("job_id"),
            BacktestJobs.status,
            BacktestJobs.ticker,
            BacktestJobs.timeframe,
            completion_time_expr,
            BacktestJobs.error_message,
        )
        .where(BacktestJobs.batch_id == batch_id)
        .order_by(BacktestJobs.created_at)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        BatchBacktestJobInfo(
            job_id=row.job_id,
            status=row.status.value,
            ticker=row.ticker,
            timeframe=row.timeframe,
            completion_time=row.completion_time,
            error_message=row.error_message,
        )
        for row in rows
    ]


async def update_batch_counters(
    db: AsyncSession,
    *,
    batch_id: BatchID,
    completed_delta: int = 0,
    failed_delta: int = 0,
) -> BacktestBatches | None:
    """
    Обновляет счетчики выполненных и неудачных задач в групповом бэктесте.

    Args:
        db: Асинхронная сессия базы данных
        batch_id: UUID группового бэктеста
        completed_delta: Изменение количества выполненных задач
        failed_delta: Изменение количества неудачных задач

    Returns:
        Обновленный объект BacktestBatches или None, если не найден
    """
    # Определяем новый статус в зависимости от счетчиков
    new_status_expr = case(
        # Если все задачи завершены (успешно или нет)
        (
            (
                BacktestBatches.completed_count
                + completed_delta
                + BacktestBatches.failed_count
                + failed_delta
            )
            == BacktestBatches.total_count,
            case(
                # Все задачи провалились
                (
                    (BacktestBatches.failed_count + failed_delta)
                    == BacktestBatches.total_count,
                    cast(
                        literal(BatchStatus.FAILED.value),
                        BacktestBatches.status.type,
                    ),
                ),
                # Все задачи успешны
                (
                    (BacktestBatches.completed_count + completed_delta)
                    == BacktestBatches.total_count,
                    cast(
                        literal(BatchStatus.COMPLETED.value),
                        BacktestBatches.status.type,
                    ),
                ),
                # Частичный успех
                else_=cast(
                    literal(BatchStatus.PARTIALLY_FAILED.value),
                    BacktestBatches.status.type,
                ),
            ),
        ),
        # Если есть хотя бы одна завершенная или проваленная задача - RUNNING
        (
            (BacktestBatches.completed_count + completed_delta > 0)
            | (BacktestBatches.failed_count + failed_delta > 0),
            cast(
                literal(BatchStatus.RUNNING.value), BacktestBatches.status.type
            ),
        ),
        # Иначе статус не меняется
        else_=BacktestBatches.status,
    )

    # Обновляем счетчики и статус
    stmt = (
        update(BacktestBatches)
        .where(BacktestBatches.id == batch_id)
        .values(
            completed_count=BacktestBatches.completed_count + completed_delta,
            failed_count=BacktestBatches.failed_count + failed_delta,
            status=new_status_expr,
        )
        .returning(BacktestBatches)
    )

    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()

    if batch:
        log.info(
            "batch.counters.updated",
            batch_id=str(batch_id),
            completed_delta=completed_delta,
            failed_delta=failed_delta,
            new_completed_count=batch.completed_count,
            new_failed_count=batch.failed_count,
            new_status=batch.status.value,
        )

    return batch


async def get_user_batch_backtests(
    db: AsyncSession,
    *,
    user_id: UserID,
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None,
    sort_by: str = "created_at",
    sort_direction: str = "desc",
) -> list[BatchBacktestSummary]:
    """
    Получает список групповых бэктестов пользователя с пагинацией и сортировкой.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя
        limit: Количество записей для возврата
        offset: Смещение от начала списка
        status_filter: Фильтр по статусу (опционально)
        sort_by: Поле для сортировки
        sort_direction: Направление сортировки (asc/desc)

    Returns:
        Список Pydantic моделей BatchBacktestSummary с данными групповых бэктестов
    """
    # Вычисляем прогресс в процентах
    progress_expr = case(
        (BacktestBatches.total_count == 0, literal(0.0)),
        else_=func.least(
            (
                (
                    BacktestBatches.completed_count
                    + BacktestBatches.failed_count
                )
                * 100.0
                / BacktestBatches.total_count
            ),
            100.0,
        ),
    ).label("progress_percentage")

    stmt = select(
        BacktestBatches.id.label("batch_id"),
        BacktestBatches.description,
        BacktestBatches.status,
        BacktestBatches.total_count,
        BacktestBatches.completed_count,
        BacktestBatches.failed_count,
        progress_expr,
        BacktestBatches.estimated_completion_time,
        BacktestBatches.created_at,
        BacktestBatches.updated_at,
    ).where(BacktestBatches.user_id == user_id)

    # Добавляем фильтр по статусу если указан
    if status_filter:
        stmt = stmt.where(BacktestBatches.status == status_filter)

    # Добавляем сортировку
    valid_sort_columns = [
        "created_at",
        "updated_at",
        "status",
        "total_count",
        "completed_count",
        "failed_count",
        "progress_percentage",
    ]
    if sort_by not in valid_sort_columns:
        sort_by = "created_at"

    # Получаем поле для сортировки
    if sort_by == "progress_percentage":
        order_field = progress_expr
    else:
        order_field = getattr(BacktestBatches, sort_by)

    if sort_direction.lower() == "desc":
        stmt = stmt.order_by(order_field.desc())
    else:
        stmt = stmt.order_by(order_field.asc())

    # Добавляем пагинацию
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        BatchBacktestSummary(
            batch_id=row.batch_id,
            description=row.description,
            status=row.status.value,
            total_count=row.total_count,
            completed_count=row.completed_count,
            failed_count=row.failed_count,
            progress_percentage=row.progress_percentage,
            estimated_completion_time=row.estimated_completion_time,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


async def get_user_batch_backtests_count(
    db: AsyncSession,
    *,
    user_id: UserID,
    status_filter: str | None = None,
) -> int:
    """
    Получает общее количество групповых бэктестов пользователя.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя
        status_filter: Фильтр по статусу (опционально)

    Returns:
        Общее количество записей
    """
    stmt = (
        select(func.count())
        .select_from(BacktestBatches)
        .where(BacktestBatches.user_id == user_id)
    )

    if status_filter:
        stmt = stmt.where(BacktestBatches.status == status_filter)

    result = await db.execute(stmt)
    return result.scalar() or 0
