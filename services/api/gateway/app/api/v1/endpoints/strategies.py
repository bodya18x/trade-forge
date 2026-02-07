"""
Эндпоинты стратегий с правильной валидацией бизнес-логики и ограничением скорости.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Request, Response, status
from redis.asyncio import Redis
from tradeforge_schemas import (
    PaginatedResponse,
    SortDirection,
    StrategyCreateRequest,
    StrategyResponse,
    StrategySortBy,
    StrategySummary,
    StrategyUpdateRequest,
    StrategyValidationRequest,
    StrategyValidationResponse,
)

from app.core.proxy_client import InternalAPIClient
from app.core.redis import get_rate_limit_redis
from app.dependencies import (
    get_current_user,
    get_current_user_id,
    get_internal_api_client,
)
from app.schemas.auth import CurrentUserInfo
from app.services.strategy_service import StrategyService

router = APIRouter()


def get_strategy_service(
    redis: Annotated[Redis, Depends(get_rate_limit_redis)],
    internal_client: Annotated[
        InternalAPIClient, Depends(get_internal_api_client)
    ],
) -> StrategyService:
    """Получает экземпляр сервиса стратегий."""
    return StrategyService(redis=redis, internal_client=internal_client)


@router.post(
    "/validate",
    response_model=StrategyValidationResponse,
    summary="Валидация определения стратегии",
    description="""
    Проверяет AST-определение стратегии и название на корректность без сохранения в базу.
    
    **Что проверяется:**
    - Корректность структуры определения стратегии (Pydantic валидация)
    - Наличие хотя бы одного условия входа в позицию (entry_buy_conditions или entry_sell_conditions)
    - Уникальность названия стратегии в рамках пользователя
    - Корректность длины названия (3-255 символов)
    
    **Возвращает:**
    - Статус валидации (is_valid)
    - Список необходимых технических индикаторов для стратегии
    - Детальный список ошибок валидации в RFC 7807 формате
    
    **При редактировании:**
    - Передайте strategy_id для исключения текущей стратегии из проверки уникальности названия
    """,
    responses={
        200: {
            "description": "Валидация прошла успешно",
            "content": {
                "application/json": {
                    "example": {
                        "is_valid": True,
                        "required_indicators": [
                            "ema_timeperiod_12",
                            "ema_timeperiod_50",
                        ],
                    }
                }
            },
        },
        422: {
            "description": "Ошибки валидации",
            "content": {
                "application/json": {
                    "example": {
                        "is_valid": False,
                        "required_indicators": [],
                        "type": "https://trade-forge.ru/errors/validation",
                        "title": "Ошибка валидации",
                        "status": 422,
                        "detail": "Одно или несколько полей не прошли валидацию.",
                        "instance": None,
                        "errors": [
                            {
                                "loc": ["definition"],
                                "msg": "Стратегия должна содержать хотя бы одно условие входа в позицию (entry_buy_conditions или entry_sell_conditions)",
                                "type": "missing_entry_conditions",
                            }
                        ],
                    }
                }
            },
        },
    },
)
async def validate_strategy_definition(
    request: Request,
    response: Response,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    strategy_service: Annotated[
        StrategyService, Depends(get_strategy_service)
    ],
    body: StrategyValidationRequest = Body(
        ...,
        description="Данные для валидации стратегии",
        examples={
            "valid_strategy": {
                "summary": "Корректная стратегия с условиями входа",
                "description": "Пример стратегии, которая пройдет валидацию успешно",
                "value": {
                    "definition": {
                        "entry_buy_conditions": {
                            "type": "CROSSOVER_UP",
                            "line1": {
                                "type": "INDICATOR_VALUE",
                                "key": "ema_timeperiod_12_value",
                            },
                            "line2": {
                                "type": "INDICATOR_VALUE",
                                "key": "ema_timeperiod_50_value",
                            },
                        },
                        "entry_sell_conditions": None,
                        "exit_conditions": {
                            "type": "CROSSOVER_DOWN",
                            "line1": {
                                "type": "INDICATOR_VALUE",
                                "key": "ema_timeperiod_12_value",
                            },
                            "line2": {
                                "type": "INDICATOR_VALUE",
                                "key": "ema_timeperiod_50_value",
                            },
                        },
                        "stop_loss": {"type": "PERCENTAGE", "percentage": 5.0},
                        "take_profit": None,
                    },
                    "name": "EMA Golden Cross Strategy",
                },
            },
            "invalid_no_entry_conditions": {
                "summary": "Некорректная стратегия без условий входа",
                "description": "Стратегия без условий входа - не пройдет валидацию",
                "value": {
                    "definition": {
                        "entry_buy_conditions": None,
                        "entry_sell_conditions": None,
                        "exit_conditions": {
                            "type": "CROSSOVER_DOWN",
                            "line1": {
                                "type": "INDICATOR_VALUE",
                                "key": "ema_timeperiod_12_value",
                            },
                            "line2": {
                                "type": "INDICATOR_VALUE",
                                "key": "ema_timeperiod_50_value",
                            },
                        },
                    },
                    "name": "Incomplete Strategy",
                },
            },
            "duplicate_name_check": {
                "summary": "Проверка уникальности названия",
                "description": "Проверка существующего названия стратегии",
                "value": {
                    "definition": {
                        "entry_buy_conditions": {
                            "type": "EQUALS",
                            "left": {
                                "type": "INDICATOR_VALUE",
                                "key": "rsi_timeperiod_14_value",
                            },
                            "right": {"type": "VALUE", "value": 30},
                        },
                        "entry_sell_conditions": None,
                        "exit_conditions": {
                            "type": "EQUALS",
                            "left": {
                                "type": "INDICATOR_VALUE",
                                "key": "rsi_timeperiod_14_value",
                            },
                            "right": {"type": "VALUE", "value": 70},
                        },
                    },
                    "name": "Existing Strategy Name",
                },
            },
        },
    ),
):
    """
    Проверяет AST-определение стратегии на корректность без сохранения в базу.
    Возвращает список необходимых индикаторов и ошибки, если они есть.
    """
    result = await strategy_service.validate_strategy_raw_request(
        user_id, request, str(request.url)
    )
    # Устанавливаем правильный HTTP статус в зависимости от результата валидации
    if not result["is_valid"]:
        # Если есть ошибки валидации - возвращаем 422
        response.status_code = 422

    return result


@router.post(
    "/",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую стратегию",
    description="""
    Создает новую торговую стратегию для текущего пользователя.
    
    **Процесс создания:**
    1. Валидирует структуру определения стратегии
    2. Проверяет доступность всех необходимых индикаторов
    3. Сохраняет стратегию в базе данных
    
    **Требования:**
    - Уникальное имя в рамках пользователя
    - Корректное AST определение стратегии
    - Все используемые индикаторы должны существовать в системе
    """,
)
async def create_strategy(
    request: StrategyCreateRequest,
    current_user: Annotated["CurrentUserInfo", Depends(get_current_user)],
    strategy_service: Annotated[
        StrategyService, Depends(get_strategy_service)
    ],
):
    """Создает новую торговую стратегию для текущего пользователя."""
    user_id = current_user.id
    subscription_tier = current_user.subscription_tier

    return await strategy_service.create_strategy(
        user_id,
        request.name,
        request.description,
        request.definition.model_dump(),
        subscription_tier,  # Передаем subscription_tier в сервис
    )


@router.get(
    "/",
    response_model=PaginatedResponse[StrategySummary],
    summary="Получить список стратегий пользователя",
    description="""
    Возвращает пагинированный список всех стратегий, принадлежащих текущему пользователю.

    **Параметры пагинации:**
    - limit: количество стратегий на страницу (1-100)
    - offset: смещение от начала списка

    **Параметры сортировки:**
    - sort_by: поле для сортировки (name, created_at, updated_at, backtests_count)
    - sort_direction: направление сортировки (asc, desc)

    **Примеры:**
    - ?sort_by=backtests_count&sort_direction=desc - сортировка по количеству бэктестов (убывание)
    - ?sort_by=name&sort_direction=asc - сортировка по названию (возрастание)
    """,
)
async def get_user_strategies(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    strategy_service: Annotated[
        StrategyService, Depends(get_strategy_service)
    ],
    limit: int = Query(
        20, ge=1, le=100, description="Количество стратегий на страницу"
    ),
    offset: int = Query(0, ge=0, description="Смещение от начала списка"),
    sort_by: StrategySortBy = Query(
        StrategySortBy.CREATED_AT, description="Поле для сортировки"
    ),
    sort_direction: SortDirection = Query(
        SortDirection.DESC, description="Направление сортировки"
    ),
):
    """Возвращает список всех стратегий, принадлежащих текущему пользователю."""
    return await strategy_service.get_user_strategies(
        user_id, limit, offset, sort_by.value, sort_direction.value
    )


@router.get(
    "/{strategy_id}",
    response_model=StrategyResponse,
    summary="Получить одну стратегию по ID",
    description="""
    Возвращает полную информацию о конкретной стратегии.
    
    **Доступ:**
    - Только владелец стратегии может получить к ней доступ
    
    **Возвращает:**
    - Полное определение стратегии (AST)
    - Метаданные (название, даты создания/обновления)
    - ID владельца
    """,
)
async def get_strategy(
    strategy_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    strategy_service: Annotated[
        StrategyService, Depends(get_strategy_service)
    ],
):
    """Возвращает детали конкретной стратегии, если она принадлежит пользователю."""
    return await strategy_service.get_strategy(user_id, strategy_id)


@router.put(
    "/{strategy_id}",
    response_model=StrategyResponse,
    summary="Обновить стратегию",
    description="""
    Обновляет имя и/или определение существующей стратегии.
    
    **Доступ:**
    - Только владелец стратегии может ее обновить
    
    **Валидация:**
    - При изменении определения проверяется корректность AST
    - Все используемые индикаторы должны существовать в системе
    
    **Поля для обновления:**
    - name: новое название стратегии (опционально)
    - definition: новое определение стратегии (опционально)
    """,
)
async def update_strategy(
    strategy_id: uuid.UUID,
    request: StrategyUpdateRequest,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    strategy_service: Annotated[
        StrategyService, Depends(get_strategy_service)
    ],
):
    """Полностью обновляет имя и определение существующей стратегии."""
    return await strategy_service.update_strategy(
        user_id,
        strategy_id,
        request.name,
        request.description,
        request.definition.model_dump() if request.definition else None,
    )


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить стратегию",
    description="""
    Удаляет стратегию пользователя.
    
    **Доступ:**
    - Только владелец стратегии может ее удалить
    
    **Ограничения:**
    - Нельзя удалить стратегию, если у нее есть активные бэктесты
    
    **Результат:**
    - HTTP 204 при успешном удалении
    - HTTP 404 если стратегия не найдена или не принадлежит пользователю
    """,
)
async def delete_strategy(
    strategy_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    strategy_service: Annotated[
        StrategyService, Depends(get_strategy_service)
    ],
):
    """Удаляет стратегию пользователя."""
    await strategy_service.delete_strategy(user_id, strategy_id)
    return None
