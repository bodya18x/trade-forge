from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session
from tradeforge_schemas import (
    LastBacktestInfo,
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

from app.crud import crud_strategies
from app.crud.exceptions import DuplicateNameError
from app.dependencies import get_current_user_id
from app.services.strategy import StrategyService
from app.types import StrategyID, UserID

router = APIRouter()


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
                        "required_indicators": ["ema_timeperiod_12"],
                        "type": "https://trade-forge.ru/errors/validation",
                        "title": "Ошибка валидации",
                        "status": 422,
                        "detail": "Одно или несколько полей не прошли валидацию.",
                        "errors": [
                            {
                                "loc": ["definition"],
                                "msg": "Стратегия должна содержать хотя бы одно условие входа в позицию",
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
    db: AsyncSession = Depends(get_db_session),
    user_id: UserID = Depends(get_current_user_id),
    body: StrategyValidationRequest = Body(
        ...,
        description="Данные для валидации стратегии",
        examples={
            "basic_strategy": {
                "summary": "Базовая стратегия с условиями входа",
                "description": "Пример корректной стратегии для валидации",
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
                    "strategy_id": None,
                },
            },
            "invalid_strategy": {
                "summary": "Некорректная стратегия без условий входа",
                "description": "Пример стратегии, которая не пройдет валидацию",
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
        },
    ),
):
    """
    Проверяет AST-определение стратегии и название на корректность без сохранения в базу.
    Возвращает список необходимых индикаторов и ошибки валидации, если они есть.
    Объединяет Pydantic ошибки схемы с кастомными бизнес-логикой ошибками.
    """
    service = StrategyService(db)
    # Используем валидированные данные от FastAPI, но добавляем свою бизнес-логику
    validation_result = await service.validate_strategy_with_business_logic(
        user_id, body.definition, body.name, body.strategy_id
    )

    # Устанавливаем правильный HTTP статус
    if not validation_result.is_valid:
        response.status_code = 422

    return validation_result


@router.post(
    "/",
    response_model=StrategyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую стратегию",
)
async def create_strategy(
    strategy_in: StrategyCreateRequest,
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Создает новую торговую стратегию для текущего пользователя."""
    # Предварительная валидация
    service = StrategyService(db)
    validation_result = await service.validate_strategy_definition(
        strategy_in.definition
    )
    if not validation_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid strategy definition: {validation_result.errors}",
        )

    # Обеспечиваем существование всех необходимых индикаторов
    await service.ensure_strategy_indicators_exist(strategy_in.definition)

    try:
        created_strategy = await crud_strategies.create_strategy(
            db, user_id=user_id, strategy=strategy_in
        )
    except DuplicateNameError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return created_strategy


@router.get(
    "/",
    response_model=PaginatedResponse[StrategySummary],
    summary="Получить список стратегий пользователя",
    description="""
    Возвращает пагинированный список стратегий пользователя с поддержкой сортировки.

    **Параметры сортировки:**
    - sort_by: поле для сортировки (name, created_at, updated_at, backtests_count)
    - sort_direction: направление сортировки (asc, desc)

    **Пример:**
    - /strategies/?sort_by=backtests_count&sort_direction=desc - сортировка по количеству бэктестов (убывание)
    - /strategies/?sort_by=name&sort_direction=asc - сортировка по названию (возрастание)
    """,
)
async def get_user_strategies(
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
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
    total = await crud_strategies.get_strategies_count_by_user(
        db, user_id=user_id
    )
    strategies_raw = await crud_strategies.get_strategies_with_backtest_stats(
        db,
        user_id=user_id,
        limit=limit,
        offset=offset,
        sort_by=sort_by.value,
        sort_direction=sort_direction.value,
    )

    # Преобразуем сырые данные в структурированные объекты
    strategies = []
    for row in strategies_raw:
        # Извлекаем объект Strategies из Row (первый элемент)
        strategy_obj = row[0]

        last_backtest = None
        if row.last_backtest_id:
            last_backtest = LastBacktestInfo(
                id=row.last_backtest_id,
                ticker=row.last_backtest_ticker,
                created_at=row.last_backtest_created_at,
                status=row.last_backtest_status,
                net_total_profit_pct=(
                    str(row.last_backtest_net_total_profit_pct)
                    if row.last_backtest_net_total_profit_pct is not None
                    else None
                ),
            )

        strategy_with_stats = StrategySummary(
            id=strategy_obj.id,
            user_id=strategy_obj.user_id,
            name=strategy_obj.name,
            description=strategy_obj.description,
            created_at=strategy_obj.created_at,
            updated_at=strategy_obj.updated_at,
            is_deleted=strategy_obj.is_deleted,
            backtests_count=row.backtests_count,
            last_backtest=last_backtest,
        )
        strategies.append(strategy_with_stats)

    return PaginatedResponse(
        total=total, limit=limit, offset=offset, items=strategies
    )


@router.get(
    "/{strategy_id}",
    response_model=StrategyResponse,
    summary="Получить одну стратегию по ID",
)
async def get_strategy(
    strategy_id: StrategyID,
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Возвращает детали конкретной стратегии, если она принадлежит пользователю."""
    strategy = await crud_strategies.get_strategy_by_id(
        db, user_id=user_id, strategy_id=strategy_id
    )
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
        )
    return strategy


@router.put(
    "/{strategy_id}",
    response_model=StrategyResponse,
    summary="Обновить стратегию",
)
async def update_strategy(
    strategy_id: StrategyID,
    strategy_in: StrategyUpdateRequest,
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Полностью обновляет имя и определение существующей стратегии."""
    # Проверяем, что стратегия вообще существует и принадлежит пользователю
    existing_strategy = await crud_strategies.get_strategy_by_id(
        db, user_id=user_id, strategy_id=strategy_id
    )
    if not existing_strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
        )

    # Валидируем новое определение стратегии
    service = StrategyService(db)
    validation_result = await service.validate_strategy_definition(
        strategy_in.definition
    )
    if not validation_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid strategy definition: {validation_result.errors}",
        )

    # Обеспечиваем существование всех необходимых индикаторов
    await service.ensure_strategy_indicators_exist(strategy_in.definition)

    try:
        updated_strategy = await crud_strategies.update_strategy(
            db,
            user_id=user_id,
            strategy_id=strategy_id,
            strategy_update=strategy_in,
        )
    except DuplicateNameError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    if not updated_strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy {strategy_id} not found",
        )

    return updated_strategy


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить стратегию",
)
async def delete_strategy(
    strategy_id: StrategyID,
    user_id: UserID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Удаляет стратегию пользователя."""
    deleted = await crud_strategies.delete_strategy(
        db, user_id=user_id, strategy_id=strategy_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found"
        )
    return None
