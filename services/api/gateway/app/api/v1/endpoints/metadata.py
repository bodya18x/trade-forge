"""
Эндпоинты метаданных - Публичные эндпоинты для тикеров, индикаторов и рынков.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from tradeforge_logger import get_logger
from tradeforge_schemas import (
    IndicatorResponse,
    MarketResponse,
    PaginatedResponse,
    TickerResponse,
    TimeframeInfo,
)

from app.core.proxy_client import InternalAPIClient
from app.core.rate_limiting import check_user_rate_limits
from app.core.redis import get_rate_limit_redis
from app.dependencies import get_current_user_id, get_internal_api_client

log = get_logger(__name__)

router = APIRouter()


@router.get(
    "/indicators",
    response_model=PaginatedResponse[IndicatorResponse],
    summary="Список доступных индикаторов",
    description="""
    Получить пагинированный список всех доступных технических индикаторов.
    
    **Категории индикаторов:**
    - **trend**: трендовые индикаторы (SMA, EMA, SuperTrend, Bollinger Bands)
    - **momentum**: осцилляторы (RSI, MACD, Stochastic)
    - **volume**: объемные индикаторы (MFI, Money Flow Index)
    - **volatility**: волатильность (ATR, Average True Range)
    
    **Сложность индикаторов:**
    - **basic**: базовые индикаторы (SMA, EMA, RSI, ATR)
    - **intermediate**: средние индикаторы (MACD, Stochastic, ADX, Bollinger Bands, MFI)
    - **advanced**: продвинутые индикаторы (SuperTrend)
    
    **Структура ответа:**
    - `total`: общее количество индикаторов
    - `limit`, `offset`: параметры пагинации
    - `items`: массив индикаторов со всей необходимой информацией
    
    **Каждый индикатор содержит:**
    - `name`: код индикатора для использования в API
    - `display_name`: человекочитаемое название
    - `parameters_schema`: JSON Schema параметров для валидации и генерации UI
    - `output_schema`: структура выходных данных индикатора
    - `key_template`: шаблон для генерации ключей в данных
    - `is_enabled`: доступен ли индикатор для использования
    
    **Примечание:**
    - Используйте `parameters_schema` для создания UI настройки параметров
    - `key_template` показывает, как формируются ключи для AST определений стратегий
    """,
)
async def get_indicators(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
    internal_client: Annotated[
        InternalAPIClient, Depends(get_internal_api_client)
    ],
):
    """
    Получить список всех доступных технических индикаторов с валидацией и rate limiting.
    """
    try:
        # Применяем ограничение скорости
        await check_user_rate_limits(redis, user_id, "GET")

        # Получаем индикаторы из внутреннего API
        response = await internal_client.get(
            path="/api/v1/metadata/indicators/system", user_id=user_id
        )

        if response.status_code != 200:
            log.error(
                "indicators.internal_api.error",
                user_id=str(user_id),
                status_code=response.status_code,
                error=response.text,
            )
            raise HTTPException(
                status_code=503, detail="Internal API is unavailable"
            )

        indicators_data = response.json()

        log.info(
            "indicators.retrieved",
            user_id=str(user_id),
            count=(
                len(indicators_data.get("items", []))
                if isinstance(indicators_data, dict)
                else "unknown"
            ),
        )

        return indicators_data

    except HTTPException:
        raise
    except Exception as e:
        log.error(
            "indicators.retrieval.failed",
            user_id=str(user_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail="Ошибка сервиса получения индикаторов"
        )


@router.get(
    "/markets",
    response_model=list[MarketResponse],
    summary="Список рынков",
    description="""
    Получить список всех доступных торговых площадок (рынков).
    
    **Доступные рынки:**
    - **MOEX Stock**: Московская биржа, фондовый рынок
    - **MOEX Currency**: Московская биржа, валютный рынок
    - **MOEX Futures**: Московская биржа, срочный рынок
    
    **Информация о рынке:**
    - Код рынка для использования в API
    - Название и описание рынка
    - Часовой пояс и часы работы
    - Статус активности
    
    **Примечание:**
    - Используйте для фильтрации тикеров по типу рынка
    """,
)
async def get_markets(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
    internal_client: Annotated[
        InternalAPIClient, Depends(get_internal_api_client)
    ],
):
    """
    Получить список всех доступных рынков с валидацией и rate limiting.
    """
    try:
        # Применяем ограничение скорости
        await check_user_rate_limits(redis, user_id, "GET")

        # Получаем рынки из внутреннего API
        response = await internal_client.get(
            path="/api/v1/metadata/markets", user_id=user_id
        )

        if response.status_code != 200:
            log.error(
                "markets.internal_api.error",
                user_id=str(user_id),
                status_code=response.status_code,
                error=response.text,
            )
            raise HTTPException(
                status_code=503, detail="Internal API is unavailable"
            )

        markets_data = response.json()

        log.info(
            "markets.retrieved",
            user_id=str(user_id),
            count=(
                len(markets_data)
                if isinstance(markets_data, list)
                else "unknown"
            ),
        )

        return markets_data

    except HTTPException:
        raise
    except Exception as e:
        log.error(
            "markets.retrieval.failed",
            user_id=str(user_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail="Ошибка сервиса получения рынков"
        )


@router.get(
    "/tickers",
    response_model=PaginatedResponse[TickerResponse],
    summary="Список тикеров",
    description="""
    Получить список всех доступных торговых инструментов (тикеров).

    **Типы инструментов:**
    - **stock**: акции российских компаний (SBER, GAZP, LKOH, и т.д.)
    - **currency**: валютные пары (USD/RUB, EUR/RUB)
    - **future**: фьючерсные контракты

    **Параметры фильтрации:**
    - **market_code**: фильтр по типу рынка (например, 'moex_stock')
    - **search**: поиск по символу или описанию тикера (например, 'SBER' или 'Сбербанк')
    - **limit**: ограничение количества тикеров (1-200)

    **Каждый тикер содержит:**
    - Символ и полное название инструмента
    - Параметры для торговли (размер лота, минимальный шаг цены)
    - Валюту торгов и ISIN код
    - Тип рынка и статус активности

    **Примеры использования:**
    - `/tickers?search=SBER` - найти все тикеры содержащие "SBER"
    - `/tickers?market_code=moex_stock` - только акции MOEX
    - `/tickers?search=банк&limit=10` - найти 10 банковских тикеров

    **Примечание:**
    - Используйте символ тикера для создания бэктестов
    - Для быстрого выбора используйте `/tickers/popular`
    - Обратите внимание на lot_size и min_step при расчете размеров позиций
    """,
)
async def get_tickers(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
    internal_client: Annotated[
        InternalAPIClient, Depends(get_internal_api_client)
    ],
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Максимальное количество тикеров в ответе",
    ),
    market_code: str | None = Query(
        None, description="Фильтр по коду рынка (например, 'moex_stock')"
    ),
    search: str | None = Query(
        None, description="Поиск по символу или описанию тикера"
    ),
):
    """
    Получить список всех доступных тикеров с валидацией и rate limiting.
    Поддерживает фильтрацию по рынку и поиск.
    """
    try:
        # Применяем ограничение скорости
        await check_user_rate_limits(redis, user_id, "GET")

        # Подготавливаем параметры
        params = {"limit": limit}
        if market_code:
            params["market_code"] = market_code
        if search:
            params["search"] = search

        # Получаем тикеры из внутреннего API
        response = await internal_client.get(
            path="/api/v1/metadata/tickers",
            user_id=user_id,
            params=params,
        )

        if response.status_code != 200:
            log.error(
                "tickers.internal_api.error",
                user_id=str(user_id),
                status_code=response.status_code,
                error=response.text,
            )
            raise HTTPException(
                status_code=503, detail="Internal API is unavailable"
            )

        tickers_data = response.json()

        log.info(
            "tickers.retrieved",
            user_id=str(user_id),
            count=(
                len(tickers_data)
                if isinstance(tickers_data, list)
                else "unknown"
            ),
            limit=limit,
        )

        return tickers_data

    except HTTPException:
        raise
    except Exception as e:
        log.error(
            "tickers.retrieval.failed",
            user_id=str(user_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail="Ошибка сервиса получения тикеров"
        )


@router.get(
    "/tickers/popular",
    response_model=list[TickerResponse],
    summary="Список популярных тикеров",
    description="""
    Получить список популярных (наиболее торгуемых) тикеров.

    **Критерии популярности:**
    - Тикеры с высокой ликвидностью (list_level = 1)
    - Наиболее активно торгуемые инструменты
    - Подходят для большинства торговых стратегий

    **Использование:**
    - Идеально для быстрого выбора тикера в UI
    - Рекомендуемые инструменты для новичков
    - Основа для создания портфелей

    **Примечание:**
    - Список ограничен 30 самыми популярными тикерами
    - Обновляется автоматически при изменении ликвидности
    """,
)
async def get_popular_tickers(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
    internal_client: Annotated[
        InternalAPIClient, Depends(get_internal_api_client)
    ],
    limit: int = Query(
        30,
        ge=1,
        le=500,
        description="Максимальное количество популярных тикеров",
    ),
):
    """
    Получить список популярных тикеров с валидацией и rate limiting.
    """
    try:
        # Применяем ограничение скорости
        await check_user_rate_limits(redis, user_id, "GET")

        # Получаем популярные тикеры из внутреннего API
        response = await internal_client.get(
            path="/api/v1/metadata/tickers/popular",
            user_id=user_id,
            params={"limit": limit},
        )

        if response.status_code != 200:
            log.error(
                "tickers.popular.internal_api.error",
                user_id=str(user_id),
                status_code=response.status_code,
                error=response.text,
            )
            raise HTTPException(
                status_code=503, detail="Internal API is unavailable"
            )

        tickers_data = response.json()

        log.info(
            "tickers.popular.retrieved",
            user_id=str(user_id),
            count=(
                len(tickers_data)
                if isinstance(tickers_data, list)
                else "unknown"
            ),
            limit=limit,
        )

        return tickers_data

    except HTTPException:
        raise
    except Exception as e:
        log.error(
            "tickers.popular.retrieval.failed",
            user_id=str(user_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Ошибка сервиса получения популярных тикеров",
        )


@router.get(
    "/timeframes",
    response_model=list[TimeframeInfo],
    summary="Список поддерживаемых таймфреймов",
    description="""
    Получить список всех поддерживаемых системой таймфреймов для бэктестинга.

    **Доступные таймфреймы:**
    - **10min**: 10-минутные свечи
    - **1h**: Часовые свечи
    - **1d**: Дневные свечи
    - **1w**: Недельные свечи
    - **1m**: Месячные свечи

    **Каждый таймфрейм содержит:**
    - `code`: код таймфрейма для использования в API
    - `name`: человекочитаемое название
    - `duration_minutes`: продолжительность в минутах
    - `is_supported`: поддерживается ли системой

    **Примечание:**
    - Используйте код таймфрейма при создании бэктестов
    - Все возвращаемые таймфреймы активно поддерживаются системой
    """,
)
async def get_timeframes(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
    internal_client: Annotated[
        InternalAPIClient, Depends(get_internal_api_client)
    ],
):
    """
    Получить список всех поддерживаемых таймфреймов с валидацией и rate limiting.
    """
    try:
        # Применяем ограничение скорости
        await check_user_rate_limits(redis, user_id, "GET")

        # Получаем таймфреймы из внутреннего API
        response = await internal_client.get(
            path="/api/v1/metadata/timeframes", user_id=user_id
        )

        if response.status_code != 200:
            log.error(
                "timeframes.internal_api.error",
                user_id=str(user_id),
                status_code=response.status_code,
                error=response.text,
            )
            raise HTTPException(
                status_code=503, detail="Internal API is unavailable"
            )

        timeframes_data = response.json()

        log.info(
            "timeframes.retrieved",
            user_id=str(user_id),
            count=(
                len(timeframes_data)
                if isinstance(timeframes_data, list)
                else "unknown"
            ),
        )

        return timeframes_data

    except HTTPException:
        raise
    except Exception as e:
        log.error(
            "timeframes.retrieval.failed",
            user_id=str(user_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail="Ошибка сервиса получения таймфреймов"
        )
