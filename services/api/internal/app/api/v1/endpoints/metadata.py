import json

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session
from tradeforge_logger import get_logger
from tradeforge_schemas import (
    MarketResponse,
    PaginatedResponse,
    TickerResponse,
    TimeframeInfo,
)

from app.cache import get_redis_client
from app.crud import crud_metadata
from app.schemas.metadata import SystemIndicatorResponse

log = get_logger(__name__)
router = APIRouter()

# TODO: хардкод, перенести в базу.
SUPPORTED_TIMEFRAMES = [
    {
        "code": "10min",
        "name": "10 минут",
        "duration_minutes": 10,
        "is_supported": True,
    },
    {
        "code": "1h",
        "name": "1 час",
        "duration_minutes": 60,
        "is_supported": True,
    },
    {
        "code": "1d",
        "name": "1 день",
        "duration_minutes": 1440,
        "is_supported": True,
    },
    {
        "code": "1w",
        "name": "1 неделя",
        "duration_minutes": 10080,
        "is_supported": True,
    },
    {
        "code": "1m",
        "name": "1 месяц",
        "duration_minutes": 43200,
        "is_supported": True,
    },
]


@router.get(
    "/indicators/system",
    response_model=PaginatedResponse[SystemIndicatorResponse],
    summary="Получить список системных индикаторов",
)
async def get_system_indicators(
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Возвращает пагинированный список всех доступных системных технических индикаторов.
    """
    total = await crud_metadata.get_total_indicators_count(db)
    indicators = await crud_metadata.get_indicators(
        db, limit=limit, offset=offset
    )
    return PaginatedResponse(
        total=total, limit=limit, offset=offset, items=indicators
    )


@router.get(
    "/markets",
    response_model=list[MarketResponse],
    summary="Получить список рынков",
)
async def get_markets(
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client),
):
    """
    Возвращает список всех торговых площадок (рынков).
    Этот ответ кэшируется на 5 минут.
    """
    cache_key = "metadata:markets"
    cached_markets = await redis.get(cache_key)
    if cached_markets:
        log.info("cache.hit", cache_key=cache_key, endpoint="get_markets")
        return json.loads(cached_markets)

    log.info("cache.miss", cache_key=cache_key, endpoint="get_markets")

    markets = await crud_metadata.get_markets(db)
    # Pydantic модели нужно сначала конвертировать в dict для JSON сериализации
    markets_dict = [
        MarketResponse.model_validate(m).model_dump() for m in markets
    ]
    await redis.set(
        cache_key, json.dumps(markets_dict), ex=300
    )  # Кэш на 5 минут

    log.info(
        "cache.set",
        cache_key=cache_key,
        endpoint="get_markets",
        ttl_seconds=300,
        items_count=len(markets_dict),
    )

    return markets_dict


@router.get(
    "/tickers",
    response_model=PaginatedResponse[TickerResponse],
    summary="Получить список тикеров",
)
async def get_tickers(
    db: AsyncSession = Depends(get_db_session),
    market_code: str | None = Query(
        None, description="Фильтр по коду рынка, например 'moex_stock'"
    ),
    search: str | None = Query(
        None, description="Поиск по символу или описанию тикера"
    ),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    Возвращает пагинированный список торгуемых инструментов (тикеров).
    Поддерживает фильтрацию по рынку и поиск по символу/описанию.
    """
    total = await crud_metadata.get_total_tickers_count(
        db, market_code=market_code, search=search
    )
    tickers = await crud_metadata.get_tickers(
        db, limit=limit, offset=offset, market_code=market_code, search=search
    )
    return PaginatedResponse(
        total=total, limit=limit, offset=offset, items=tickers
    )


@router.get(
    "/tickers/popular",
    response_model=list[TickerResponse],
    summary="Получить список популярных тикеров",
)
async def get_popular_tickers(
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(
        30,
        ge=1,
        le=500,
        description="Максимальное количество популярных тикеров",
    ),
):
    """
    Возвращает список популярных тикеров (с list_level = 1).
    Это наиболее торгуемые и ликвидные инструменты.
    """
    tickers = await crud_metadata.get_popular_tickers(db, limit=limit)
    return tickers


@router.get(
    "/timeframes",
    response_model=list[TimeframeInfo],
    summary="Получить список поддерживаемых таймфреймов",
)
async def get_timeframes():
    """
    Возвращает фиксированный список таймфреймов, поддерживаемых системой.
    """
    return SUPPORTED_TIMEFRAMES
