"""
Эндпоинты бэктестов с правильной валидацией бизнес-логики и ограничением скорости.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from redis.asyncio import Redis
from tradeforge_schemas import (
    BacktestCreateRequest,
    BacktestFullResponse,
    BacktestJobInfo,
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

from app.core.proxy_client import InternalAPIClient
from app.core.redis import get_rate_limit_redis
from app.dependencies import (
    get_current_user,
    get_current_user_id,
    get_internal_api_client,
)
from app.schemas.auth import CurrentUserInfo
from app.services.backtest_service import BacktestService
from app.services.batch_backtest_service import BatchBacktestService

router = APIRouter()


def get_backtest_service(
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
    internal_client: Annotated[
        InternalAPIClient, Depends(get_internal_api_client)
    ],
) -> BacktestService:
    """Получает экземпляр сервиса бэктестов."""
    return BacktestService(redis=redis, internal_client=internal_client)


def get_batch_backtest_service(
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
    internal_client: Annotated[
        InternalAPIClient, Depends(get_internal_api_client)
    ],
) -> BatchBacktestService:
    """Получает экземпляр сервиса групповых бэктестов."""
    return BatchBacktestService(redis=redis, internal_client=internal_client)


@router.post(
    "/",
    response_model=BacktestJobInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Запустить новый бэктест",
    description="""
    Асинхронно запускает задачу на проведение бэктеста стратегии.

    **Процесс выполнения:**
    1. Проверяет лимиты пользователя (количество одновременных бэктестов)
    2. Валидирует параметры бэктеста (даты, таймфрейм, тикер)
    3. Проверяет доступ к указанной стратегии
    4. Создает задачу в базе данных
    5. Отправляет задачу в очередь Kafka на обработку

    **Идемпотентность:**
    - Поддерживается через заголовок `Idempotency-Key`
    - Повторные запросы с тем же ключом вернут ссылку на существующий бэктест

    **Лимиты:**
    - Максимум 5 одновременных бэктестов на пользователя
    - Максимальный период бэктеста: 3 года

    **Возвращает:**
    - HTTP 201 с информацией о созданной задаче
    - Статус задачи: PENDING (ожидает обработку)
    """,
)
async def submit_backtest_job(
    request: BacktestCreateRequest,
    current_user: Annotated["CurrentUserInfo", Depends(get_current_user)],
    backtest_service: Annotated[
        BacktestService, Depends(get_backtest_service)
    ],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Ключ для идемпотентности запроса",
        ),
    ] = None,
):
    """
    Асинхронно запускает задачу на проведение бэктеста.
    """
    user_id = current_user.id
    subscription_tier = current_user.subscription_tier

    return await backtest_service.create_backtest(
        user_id=user_id,
        strategy_id=request.strategy_id,
        ticker=request.ticker,
        timeframe=request.timeframe,
        start_date=request.start_date,
        end_date=request.end_date,
        simulation_params=request.simulation_params.model_dump(),
        subscription_tier=subscription_tier,
        idempotency_key=idempotency_key,
    )


# === BATCH BACKTEST ENDPOINTS ===
@router.post(
    "/batch",
    response_model=BatchBacktestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать групповой бэктест",
    description="""
    Создает группу бэктестов и запускает их выполнение.

    **Лимиты:**
    - Максимум 50 бэктестов в одной группе
    - Проверяется дневной лимит бэктестов
    - Проверяется лимит одновременных бэктестов
    - Если запрошенное количество превышает доступное - возвращается ошибка 429

    **Идемпотентность:**
    - Используйте заголовок Idempotency-Key для предотвращения дублирования
    - Повторные запросы с тем же ключом вернут ссылку на существующую группу

    **Лимиты:**
    - Максимум 50 бэктестов в одной группе
    - Проверяется дневной лимит бэктестов
    - Проверяется лимит одновременных бэктестов
    - Если запрошенное количество превышает доступное - возвращается ошибка 429

    **Возвращает:**
    - HTTP 201 с информацией о созданной группе
    - Список всех индивидуальных задач с их статусами
    - Оценку времени завершения группы
    """,
)
async def create_batch_backtests(
    request: BatchBacktestCreateRequest,
    current_user: Annotated["CurrentUserInfo", Depends(get_current_user)],
    batch_backtest_service: Annotated[
        BatchBacktestService, Depends(get_batch_backtest_service)
    ],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Ключ для идемпотентности запроса",
        ),
    ] = None,
):
    """
    Создает групповой бэктест с проверкой лимитов.
    """
    user_id = current_user.id
    subscription_tier = current_user.subscription_tier

    # Преобразуем Pydantic модели в словари с правильной сериализацией UUID
    backtests_data = [
        backtest.model_dump(mode="json") for backtest in request.backtests
    ]

    return await batch_backtest_service.create_batch_backtests(
        user_id=user_id,
        description=request.description,
        backtests=backtests_data,
        subscription_tier=subscription_tier,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/batch/{batch_id}",
    response_model=BatchBacktestResponse,
    summary="Получить статус группового бэктеста",
    description="""
    Возвращает полную информацию о групповом бэктесте и статусах всех задач.

    **Возвращает:**
    - Общую информацию о группе (описание, статус, счетчики)
    - Детальную информацию о каждой индивидуальной задаче
    - Счетчики выполненных и неудачных задач
    - Оценку времени завершения оставшихся задач
    """,
)
async def get_batch_backtest_status(
    batch_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    batch_backtest_service: Annotated[
        BatchBacktestService, Depends(get_batch_backtest_service)
    ],
):
    """
    Возвращает статус группового бэктеста и всех индивидуальных задач.
    """
    return await batch_backtest_service.get_batch_status(user_id, batch_id)


@router.get(
    "/batch",
    response_model=PaginatedResponse[BatchBacktestSummary],
    summary="Получить список групповых бэктестов пользователя",
    description="""
    Возвращает пагинированный список всех групповых бэктестов пользователя.

    **Параметры пагинации:**
    - limit: количество групп на страницу (1-100)
    - offset: смещение от начала списка

    **Фильтрация:**
    - status_filter: опциональный фильтр по статусу группы

    **Параметры сортировки:**
    - sort_by: поле для сортировки (created_at, status, total_count, progress, и др.)
    - sort_direction: направление сортировки (asc, desc)

    **Примеры:**
    - ?sort_by=progress_percentage&sort_direction=desc - сортировка по проценту выполнения (убывание)
    - ?sort_by=created_at&sort_direction=asc - сортировка по времени создания (возрастание)
    - ?status_filter=RUNNING - показать только выполняющиеся группы

    **Краткая информация:**
    - Общие метаданные группы (описание, время создания)
    - Текущий статус и прогресс
    - Счетчики задач (общее, выполнено, ошибки)
    - Процент выполнения группы
    """,
)
async def get_user_batch_backtests(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    batch_backtest_service: Annotated[
        BatchBacktestService, Depends(get_batch_backtest_service)
    ],
    limit: int = Query(
        50, ge=1, le=100, description="Количество групп на страницу"
    ),
    offset: int = Query(0, ge=0, description="Смещение от начала списка"),
    status_filter: BatchStatusEnum | None = Query(
        None, description="Фильтр по статусу группы (опционально)"
    ),
    sort_by: BatchSortBy = Query(
        BatchSortBy.CREATED_AT, description="Поле для сортировки"
    ),
    sort_direction: SortDirection = Query(
        SortDirection.DESC, description="Направление сортировки"
    ),
):
    """
    Возвращает пагинированный список всех групповых бэктестов пользователя.
    """

    return await batch_backtest_service.get_user_batch_backtests(
        user_id,
        limit,
        offset,
        status_filter.value if status_filter else None,
        sort_by.value,
        sort_direction.value,
    )


@router.get(
    "/{job_id}",
    response_model=BacktestFullResponse,
    summary="Получить статус и результаты бэктеста",
    description="""
    Возвращает полную информацию о задаче на бэктест и ее результаты.
    
    **Статусы задачи:**
    - PENDING: задача в очереди, ожидает обработку
    - RUNNING: задача выполняется
    - COMPLETED: задача выполнена успешно, результаты доступны
    - FAILED: задача завершилась с ошибкой
    
    **Доступ:**
    - Только владелец стратегии может получить доступ к бэктесту
    
    **Результаты:**
    - При статусе COMPLETED возвращаются полные результаты:
      - Метрики эффективности (доходность, просадка, коэффициенты Шарпа/Сортино)
      - Полный список всех симуляционных сделок
      - Детали по каждой сделке (вход, выход, P&L, комиссия)
    """,
)
async def get_backtest_status_and_results(
    job_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    backtest_service: Annotated[
        BacktestService, Depends(get_backtest_service)
    ],
):
    """
    Возвращает информацию о задаче на бэктест и ее результаты, если они готовы.
    """
    return await backtest_service.get_backtest(user_id, job_id)


@router.get(
    "/",
    response_model=PaginatedResponse[BacktestSummary],
    summary="Получить список бэктестов пользователя",
    description="""
    Возвращает пагинированный список всех бэктестов пользователя.

    **Параметры пагинации:**
    - limit: количество бэктестов на страницу (1-100)
    - offset: смещение от начала списка

    **Фильтрация:**
    - strategy_id: опциональный фильтр по конкретной стратегии

    **Параметры сортировки:**
    - sort_by: поле для сортировки (created_at, net_total_profit_pct, total_trades, win_rate, и др.)
    - sort_direction: направление сортировки (asc, desc)

    **Примеры:**
    - ?sort_by=net_total_profit_pct&sort_direction=desc - сортировка по доходности (убывание)
    - ?sort_by=win_rate&sort_direction=asc - сортировка по проценту выигрышных сделок (возрастание)
    - ?sort_by=max_drawdown_pct&sort_direction=asc - сортировка по просадке (возрастание)

    **Краткая информация:**
    - Общие метаданные (тикер, таймфрейм, период)
    - Текущий статус задачи
    - Все доступные метрики (доходность, просадка, количество сделок и т.д.)

    **Примечание:**
    - Метрики доступны только для завершенных бэктестов (COMPLETED)
    """,
)
async def get_user_backtests(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    backtest_service: Annotated[
        BacktestService, Depends(get_backtest_service)
    ],
    limit: int = Query(
        50, ge=1, le=100, description="Количество бэктестов на страницу"
    ),
    offset: int = Query(0, ge=0, description="Смещение от начала списка"),
    strategy_id: uuid.UUID | None = Query(
        None, description="Фильтр по конкретной стратегии (опционально)"
    ),
    sort_by: BacktestSortBy = Query(
        BacktestSortBy.CREATED_AT, description="Поле для сортировки"
    ),
    sort_direction: SortDirection = Query(
        SortDirection.DESC, description="Направление сортировки"
    ),
):
    """
    Возвращает пагинированный список всех бэктестов пользователя.
    Опционально фильтрует по конкретной стратегии.
    """
    return await backtest_service.get_user_backtests(
        user_id,
        limit,
        offset,
        strategy_id,
        sort_by.value,
        sort_direction.value,
    )
