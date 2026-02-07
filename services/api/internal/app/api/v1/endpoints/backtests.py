from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import JobStatus, get_db_session
from tradeforge_schemas import (
    BacktestCreateRequest,
    BacktestFullResponse,
    BacktestJobInfo,
    BacktestResults,
    BacktestSortBy,
    BacktestSummary,
    BatchBacktestCreateRequest,
    BatchBacktestResponse,
    BatchBacktestSummary,
    BatchSortBy,
    BatchStatusEnum,
    PaginatedResponse,
    SortDirection,
)

from app.cache import get_redis_client
from app.crud import crud_backtests
from app.dependencies import get_current_user_id
from app.services.backtest import BacktestService
from app.services.batch_backtest import BatchBacktestService
from app.types import BacktestJobID, BatchID, StrategyID, UserID

router = APIRouter()


@router.post(
    "/",
    response_model=BacktestJobInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Запустить новый бэктест",
)
async def submit_backtest_job(
    backtest_in: BacktestCreateRequest,
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client),
    idempotency_key: Annotated[str | None, Header()] = None,
):
    """
    Асинхронно запускает задачу на проведение бэктеста.

    - Валидирует все входные параметры (тикер, таймфрейм, даты, параметры симуляции).
    - Проверяет лимиты пользователя.
    - Поддерживает идемпотентность через заголовок `Idempotency-Key`.
    - Создает задачу и отправляет ее в очередь на обработку.
    - Возвращает `201 Created` с информацией о созданной задаче.
    """
    service = BacktestService(db=db, redis=redis, user_id=user_id)
    job = await service.submit_backtest(backtest_in, idempotency_key)
    return job


# === BATCH BACKTEST ENDPOINTS ===


@router.post(
    "/batch",
    response_model=BatchBacktestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать групповой бэктест",
    description="""
    Создает группу бэктестов и запускает их выполнение.

    **Валидация:**
    - Проверяет все параметры каждого бэктеста
    - Валидирует доступ к стратегиям
    - Проверяет лимиты пользователя

    **Процесс:**
    1. Создает запись группового бэктеста
    2. Создает индивидуальные задачи
    3. Отправляет задачи в Kafka на выполнение
    4. Возвращает информацию о группе и всех задачах

    **Ограничения:**
    - Максимум 50 бэктестов в одной группе
    - Учитываются лимиты на одновременные бэктесты
    """,
)
async def submit_batch_backtest_jobs(
    batch_request: BatchBacktestCreateRequest,
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client),
    idempotency_key: Annotated[str | None, Header()] = None,
):
    """
    Создает групповой бэктест и запускает все индивидуальные задачи.
    """
    service = BatchBacktestService(db=db, redis=redis, user_id=user_id)

    # Преобразуем Pydantic модели в словари для сервиса
    backtests_data = [
        backtest.model_dump() for backtest in batch_request.backtests
    ]

    batch_response = await service.submit_batch_backtest(
        description=batch_request.description,
        backtests=backtests_data,
        idempotency_key=idempotency_key,
    )

    return batch_response


@router.get(
    "/batch/{batch_id}",
    response_model=BatchBacktestResponse,
    summary="Получить статус группового бэктеста",
    description="""
    Возвращает текущий статус группового бэктеста и всех индивидуальных задач.

    **Информация включает:**
    - Общий статус группы (PENDING, RUNNING, COMPLETED, FAILED, PARTIALLY_FAILED)
    - Счетчики выполненных и неудачных задач
    - Процент выполнения
    - Детальную информацию о каждой индивидуальной задаче
    - Оценку времени завершения

    **Доступ:**
    - Только владелец группы может получить доступ к информации
    """,
)
async def get_batch_backtest_status(
    batch_id: BatchID,
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client),
):
    """
    Возвращает статус группового бэктеста.
    """
    service = BatchBacktestService(db=db, redis=redis, user_id=user_id)
    batch_data = await service.get_batch_status(batch_id)

    if not batch_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch backtest not found or access denied",
        )

    return batch_data


@router.get(
    "/batch",
    response_model=PaginatedResponse[BatchBacktestSummary],
    summary="Получить список групповых бэктестов пользователя",
    description="""
    Возвращает пагинированный список всех групповых бэктестов пользователя.

    **Параметры фильтрации:**
    - status: фильтр по статусу группы

    **Параметры сортировки:**
    - sort_by: поле для сортировки (created_at, status, total_count, и др.)
    - sort_direction: направление сортировки (asc, desc)

    **Пагинация:**
    - limit: количество групп на страницу (1-100)
    - offset: смещение от начала списка

    **Краткая информация включает:**
    - Основные метаданные группы
    - Текущий статус и прогресс
    - Счетчики задач
    """,
)
async def get_user_batch_backtests(
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client),
    limit: int = Query(
        50, ge=1, le=100, description="Количество групп на страницу"
    ),
    offset: int = Query(0, ge=0, description="Смещение от начала списка"),
    status_filter: BatchStatusEnum | None = Query(
        None, description="Фильтр по статусу группы"
    ),
    sort_by: BatchSortBy = Query(
        BatchSortBy.CREATED_AT, description="Поле для сортировки"
    ),
    sort_direction: SortDirection = Query(
        SortDirection.DESC, description="Направление сортировки"
    ),
):
    """
    Возвращает пагинированный список групповых бэктестов пользователя.
    """
    service = BatchBacktestService(db=db, redis=redis, user_id=user_id)

    result = await service.get_user_batch_backtests(
        limit=limit,
        offset=offset,
        status_filter=status_filter.value if status_filter else None,
        sort_by=sort_by.value,
        sort_direction=sort_direction.value,
    )

    return PaginatedResponse(
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
        items=result["items"],
    )


@router.get(
    "/{job_id}",
    response_model=BacktestFullResponse,
    summary="Получить статус и результаты бэктеста",
)
async def get_backtest_status_and_results(
    job_id: BacktestJobID,
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Возвращает информацию о задаче на бэктест и ее результаты, если они готовы.
    """
    job = await crud_backtests.get_backtest_job_by_id(
        db, user_id=user_id, job_id=job_id
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest job not found.",
        )

    result_data = None

    if job.status == JobStatus.COMPLETED:
        result = await crud_backtests.get_backtest_result_by_job_id(
            db, job_id=job_id
        )
        if result:
            # Преобразуем данные для совместимости со схемой
            processed_result = result.to_dict()
            result_data = BacktestResults.model_validate(processed_result)

    return BacktestFullResponse(job=job, results=result_data)


@router.get(
    "/",
    response_model=PaginatedResponse[BacktestSummary],
    summary="Получить список бэктестов пользователя",
)
async def get_user_backtests(
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(
        50, ge=1, le=100, description="Количество бэктестов на страницу"
    ),
    offset: int = Query(0, ge=0, description="Смещение от начала списка"),
    strategy_id: StrategyID | None = None,
    sort_by: BacktestSortBy = Query(
        BacktestSortBy.CREATED_AT, description="Поле для сортировки"
    ),
    sort_direction: SortDirection = Query(
        SortDirection.DESC, description="Направление сортировки"
    ),
):
    """
    Возвращает пагинированный список всех бэктестов пользователя с поддержкой сортировки.
    Опционально фильтрует по конкретной стратегии.

    **Параметры сортировки:**
    - sort_by: поле для сортировки (created_at, net_total_profit_pct, total_trades, win_rate, и др.)
    - sort_direction: направление сортировки (asc, desc)

    **Примеры:**
    - /backtests/?sort_by=net_total_profit_pct&sort_direction=desc - сортировка по доходности (убывание)
    - /backtests/?sort_by=win_rate&sort_direction=asc - сортировка по проценту выигрышных сделок (возрастание)
    """
    total = await crud_backtests.get_user_backtest_jobs_count(
        db, user_id=user_id, strategy_id=strategy_id
    )
    jobs = await crud_backtests.get_user_backtest_jobs(
        db,
        user_id=user_id,
        limit=limit,
        offset=offset,
        strategy_id=strategy_id,
        sort_by=sort_by.value,
        sort_direction=sort_direction.value,
    )

    return PaginatedResponse(
        total=total, limit=limit, offset=offset, items=jobs
    )
