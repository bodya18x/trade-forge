"""
CRUD операции для работы с бэктестами.

Этот модуль содержит функции для создания, получения и управления задачами бэктестинга.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import BacktestJobs, BacktestResults, JobStatus, Strategies
from tradeforge_logger import get_logger
from tradeforge_schemas import BacktestCreateRequest, BacktestSummary

from app.crud.helpers import (
    filter_active_strategies,
    get_backtest_sort_clauses,
    model_to_dict,
)
from app.types import BacktestJobID, BatchID, StrategyID, UserID

log = get_logger(__name__)


async def create_backtest_job(
    db: AsyncSession,
    user_id: UserID,
    backtest_in: BacktestCreateRequest,
    strategy_snapshot: dict,
    parsed_start_date: datetime,
    parsed_end_date: datetime,
    batch_id: BatchID | None = None,
    counts_towards_limit: bool = True,
) -> BacktestJobs:
    """
    Создает новую запись о задаче на бэктест в БД.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя, создающего задачу
        backtest_in: Pydantic схема с параметрами бэктеста
        strategy_snapshot: Снапшот определения стратегии на момент создания
        parsed_start_date: Дата начала бэктеста с timezone
        parsed_end_date: Дата окончания бэктеста с timezone
        batch_id: UUID группового бэктеста (если задача является частью группы)
        counts_towards_limit: Учитывается ли задача в лимитах пользователя

    Returns:
        Созданный объект BacktestJobs
    """
    job = BacktestJobs(
        id=uuid.uuid4(),
        user_id=user_id,
        strategy_id=backtest_in.strategy_id,
        ticker=backtest_in.ticker,
        timeframe=backtest_in.timeframe,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        status=JobStatus.PENDING,
        strategy_definition_snapshot=strategy_snapshot,
        simulation_params=(
            backtest_in.simulation_params.model_dump()
            if backtest_in.simulation_params
            else None
        ),
        batch_id=batch_id,
        counts_towards_limit=counts_towards_limit,
    )

    db.add(job)
    await db.flush()

    log.debug(
        "backtest.job.created",
        job_id=str(job.id),
        user_id=str(user_id),
        strategy_id=str(backtest_in.strategy_id),
        ticker=backtest_in.ticker,
        timeframe=backtest_in.timeframe,
        batch_id=str(batch_id) if batch_id else None,
        counts_towards_limit=counts_towards_limit,
    )

    return job


async def create_failed_backtest_job(
    db: AsyncSession,
    user_id: UserID,
    backtest_in: BacktestCreateRequest,
    strategy_snapshot: dict,
    parsed_start_date: datetime,
    parsed_end_date: datetime,
    error_message: str,
    batch_id: BatchID | None = None,
) -> BacktestJobs:
    """
    Создает запись о задаче на бэктест со статусом FAILED.

    Используется для задач, которые не прошли pre-validation (например, нет данных).
    Такие задачи НЕ учитываются в лимитах пользователя (counts_towards_limit=FALSE).

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя
        backtest_in: Pydantic схема с параметрами бэктеста
        strategy_snapshot: Снапшот определения стратегии
        parsed_start_date: Дата начала бэктеста с timezone
        parsed_end_date: Дата окончания бэктеста с timezone
        error_message: Сообщение об ошибке валидации
        batch_id: UUID группового бэктеста (если задача является частью группы)

    Returns:
        Созданный объект BacktestJobs со статусом FAILED
    """
    job = BacktestJobs(
        id=uuid.uuid4(),
        user_id=user_id,
        strategy_id=backtest_in.strategy_id,
        ticker=backtest_in.ticker,
        timeframe=backtest_in.timeframe,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        status=JobStatus.FAILED,
        error_message=error_message,
        strategy_definition_snapshot=strategy_snapshot,
        simulation_params=(
            backtest_in.simulation_params.model_dump()
            if backtest_in.simulation_params
            else None
        ),
        batch_id=batch_id,
        counts_towards_limit=False,  # НЕ учитываем в лимитах
    )

    db.add(job)
    await db.flush()

    log.info(
        "backtest.job.created.as_failed",
        job_id=str(job.id),
        user_id=str(user_id),
        strategy_id=str(backtest_in.strategy_id),
        ticker=backtest_in.ticker,
        timeframe=backtest_in.timeframe,
        error_message=error_message,
        batch_id=str(batch_id) if batch_id else None,
    )

    return job


async def get_backtest_job_by_id(
    db: AsyncSession, user_id: UserID, job_id: BacktestJobID
) -> BacktestJobs | None:
    """
    Получает задачу по ID, проверяя принадлежность пользователю и исключая удаленные стратегии.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя для проверки доступа
        job_id: UUID задачи бэктеста

    Returns:
        Объект BacktestJobs или None, если задача не найдена или доступ запрещен
    """
    stmt = (
        select(BacktestJobs)
        .outerjoin(Strategies, BacktestJobs.strategy_id == Strategies.id)
        .where(
            BacktestJobs.id == job_id,
            BacktestJobs.user_id == user_id,
            filter_active_strategies(),
        )
    )

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_backtest_result_by_job_id(
    db: AsyncSession, job_id: BacktestJobID
) -> BacktestResults | None:
    """
    Получает результаты бэктеста по ID задачи.

    Args:
        db: Асинхронная сессия базы данных
        job_id: UUID задачи бэктеста

    Returns:
        Объект BacktestResults или None, если результаты не найдены
    """
    stmt = select(BacktestResults).where(BacktestResults.job_id == job_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_active_jobs_count(db: AsyncSession, user_id: UserID) -> int:
    """
    Считает количество активных (PENDING, RUNNING) задач для пользователя.

    Учитывает только задачи с counts_towards_limit=TRUE, исключая удаленные стратегии.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя

    Returns:
        Количество активных задач
    """
    stmt = (
        select(func.count())
        .select_from(BacktestJobs)
        .outerjoin(Strategies, BacktestJobs.strategy_id == Strategies.id)
        .where(
            BacktestJobs.user_id == user_id,
            BacktestJobs.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            BacktestJobs.counts_towards_limit.is_(True),
            filter_active_strategies(),
        )
    )

    result = await db.execute(stmt)
    return result.scalar_one()


async def get_user_backtest_jobs(
    db: AsyncSession,
    user_id: UserID,
    limit: int,
    offset: int,
    strategy_id: StrategyID | None = None,
    sort_by: str = "created_at",
    sort_direction: str = "desc",
) -> list[BacktestSummary]:
    """
    Получает пагинированный список задач на бэктест для пользователя с полными метриками.

    Исключает задачи для удаленных стратегий.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя
        limit: Максимальное количество результатов
        offset: Смещение для пагинации
        strategy_id: Опциональный фильтр по UUID стратегии
        sort_by: Поле для сортировки (created_at, net_total_profit_pct и т.д.)
        sort_direction: Направление сортировки (asc или desc)

    Returns:
        Список Pydantic моделей BacktestSummary с данными задач и метриками
    """
    # Базовый запрос с JOIN
    stmt = (
        select(
            BacktestJobs,
            # Извлекаем метрики из JSONB
            # Базовые метрики
            func.coalesce(
                BacktestResults.metrics["roi"].as_float(),
                BacktestResults.metrics["net_total_profit_pct"].as_float(),
            ).label("roi"),
            BacktestResults.metrics["total_trades"]
            .as_float()
            .label("total_trades"),
            BacktestResults.metrics["win_rate"].as_float().label("win_rate"),
            BacktestResults.metrics["max_drawdown_pct"]
            .as_float()
            .label("max_drawdown_pct"),
            # Балансы
            BacktestResults.metrics["initial_balance"]
            .as_float()
            .label("initial_balance"),
            BacktestResults.metrics["net_final_balance"]
            .as_float()
            .label("net_final_balance"),
            BacktestResults.metrics["net_total_profit_pct"]
            .as_float()
            .label("net_total_profit_pct"),
            # Статистика по сделкам
            BacktestResults.metrics["wins"].as_float().label("wins"),
            BacktestResults.metrics["losses"].as_float().label("losses"),
            BacktestResults.metrics["profit_factor"]
            .as_float()
            .label("profit_factor"),
            BacktestResults.metrics["sharpe_ratio"]
            .as_float()
            .label("sharpe_ratio"),
            BacktestResults.metrics["stability_score"]
            .as_float()
            .label("stability_score"),
            # Средние значения
            BacktestResults.metrics["avg_net_profit_pct"]
            .as_float()
            .label("avg_net_profit_pct"),
            BacktestResults.metrics["net_profit_std_dev"]
            .as_float()
            .label("net_profit_std_dev"),
            BacktestResults.metrics["avg_win_pct"]
            .as_float()
            .label("avg_win_pct"),
            BacktestResults.metrics["avg_loss_pct"]
            .as_float()
            .label("avg_loss_pct"),
            # Последовательности
            BacktestResults.metrics["max_consecutive_wins"]
            .as_float()
            .label("max_consecutive_wins"),
            BacktestResults.metrics["max_consecutive_losses"]
            .as_float()
            .label("max_consecutive_losses"),
        )
        .outerjoin(Strategies, BacktestJobs.strategy_id == Strategies.id)
        .outerjoin(BacktestResults, BacktestJobs.id == BacktestResults.job_id)
        .where(
            BacktestJobs.user_id == user_id,
            filter_active_strategies(),
        )
    )

    # Добавляем фильтр по strategy_id если указан
    if strategy_id:
        stmt = stmt.where(BacktestJobs.strategy_id == strategy_id)

    # Применяем сортировку через хелпер
    order_clauses = get_backtest_sort_clauses(sort_by, sort_direction)
    for clause in order_clauses:
        stmt = stmt.order_by(clause)

    # Применяем пагинацию
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()

    # Преобразуем результат в список Pydantic моделей
    jobs_list = []
    for row in rows:
        job = row.BacktestJobs  # BacktestJobs объект из именованного кортежа
        job_dict = {
            **model_to_dict(job),
            "status": job.status.value,
            # Добавляем метрики через именованные атрибуты
            "roi": row.roi,
            "total_trades": row.total_trades,
            "win_rate": row.win_rate,
            "max_drawdown_pct": row.max_drawdown_pct,
            "initial_balance": row.initial_balance,
            "net_final_balance": row.net_final_balance,
            "net_total_profit_pct": row.net_total_profit_pct,
            "wins": row.wins,
            "losses": row.losses,
            "profit_factor": row.profit_factor,
            "sharpe_ratio": row.sharpe_ratio,
            "stability_score": row.stability_score,
            "avg_net_profit_pct": row.avg_net_profit_pct,
            "net_profit_std_dev": row.net_profit_std_dev,
            "avg_win_pct": row.avg_win_pct,
            "avg_loss_pct": row.avg_loss_pct,
            "max_consecutive_wins": row.max_consecutive_wins,
            "max_consecutive_losses": row.max_consecutive_losses,
        }
        jobs_list.append(BacktestSummary(**job_dict))

    return jobs_list


async def get_user_backtest_jobs_count(
    db: AsyncSession, user_id: UserID, strategy_id: StrategyID | None = None
) -> int:
    """
    Считает общее количество задач на бэктест для пользователя.

    Исключает задачи для удаленных стратегий.

    Args:
        db: Асинхронная сессия базы данных
        user_id: UUID пользователя
        strategy_id: Опциональный фильтр по UUID стратегии

    Returns:
        Общее количество задач
    """
    stmt = (
        select(func.count())
        .select_from(BacktestJobs)
        .outerjoin(Strategies, BacktestJobs.strategy_id == Strategies.id)
        .where(
            BacktestJobs.user_id == user_id,
            filter_active_strategies(),
        )
    )

    # Добавляем фильтр по strategy_id если указан
    if strategy_id:
        stmt = stmt.where(BacktestJobs.strategy_id == strategy_id)

    result = await db.execute(stmt)
    return result.scalar_one()


async def update_job_status(
    db: AsyncSession,
    job_id: BacktestJobID,
    status: JobStatus,
    error_message: str | None = None,
) -> None:
    """
    Обновляет статус задачи на бэктест.

    Args:
        db: Асинхронная сессия базы данных
        job_id: UUID задачи
        status: Новый статус задачи
        error_message: Опциональное сообщение об ошибке
    """
    stmt = select(BacktestJobs).where(BacktestJobs.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if job:
        old_status = job.status
        job.status = status
        job.error_message = error_message
        await db.flush()

        log.info(
            "backtest.job.status.updated",
            job_id=str(job_id),
            old_status=old_status.value,
            new_status=status.value,
            error_message=error_message,
        )
