"""
CRUD операции для работы со стратегиями.

Использует SQLAlchemy 2.* синтаксис с моделями из tradeforge_db.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import BacktestJobs, BacktestResults, Strategies
from tradeforge_logger import get_logger
from tradeforge_schemas import StrategyCreateRequest, StrategyUpdateRequest

from app.crud.exceptions import DuplicateNameError
from app.types import StrategyID, UserID

log = get_logger(__name__)


async def create_strategy(
    db: AsyncSession, user_id: UserID, strategy: StrategyCreateRequest
):
    """
    Создает новую стратегию для пользователя.

    Args:
        db: Асинхронная сессия БД
        user_id: UUID пользователя
        strategy: Данные для создания стратегии

    Returns:
        Объект Strategies с данными созданной стратегии

    Raises:
        DuplicateNameError: Если стратегия с таким именем уже существует
    """
    # Lazy import для избежания циклической зависимости
    from app.services.strategy.indicator_key_validator import (
        IndicatorKeyValidator,
        normalize_strategy_definition,
    )

    # Проверяем уникальность названия перед созданием
    name_exists = await check_strategy_name_exists(
        db, user_id=user_id, name=strategy.name
    )
    if name_exists:
        raise DuplicateNameError("Strategy", strategy.name)

    # Нормализуем definition (убираем .0 из integer параметров)
    validator = IndicatorKeyValidator()
    normalized_definition = normalize_strategy_definition(
        strategy.definition.model_dump(), validator
    )

    new_strategy = Strategies(
        id=uuid.uuid4(),
        user_id=user_id,
        name=strategy.name,
        description=strategy.description,
        definition=normalized_definition,
        is_deleted=False,
    )

    db.add(new_strategy)
    await db.flush()

    log.info(
        "strategy.created",
        strategy_id=str(new_strategy.id),
        user_id=str(user_id),
        strategy_name=strategy.name,
    )

    return new_strategy


async def get_strategy_by_id(
    db: AsyncSession, user_id: UserID, strategy_id: StrategyID
):
    """
    Получает одну стратегию по ID, проверяя принадлежность пользователю.

    Args:
        db: Асинхронная сессия БД
        user_id: UUID пользователя
        strategy_id: UUID стратегии

    Returns:
        Объект Strategies или None
    """
    stmt = select(Strategies).where(
        Strategies.id == strategy_id,
        Strategies.user_id == user_id,
        ~Strategies.is_deleted,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_strategies_by_user(
    db: AsyncSession, user_id: UserID, limit: int, offset: int
):
    """
    Получает список стратегий пользователя.

    Args:
        db: Асинхронная сессия БД
        user_id: UUID пользователя
        limit: Количество записей для возврата
        offset: Смещение от начала списка

    Returns:
        Список объектов Strategies
    """
    stmt = (
        select(Strategies)
        .where(
            Strategies.user_id == user_id,
            ~Strategies.is_deleted,
        )
        .order_by(Strategies.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_strategies_with_backtest_stats(
    db: AsyncSession,
    user_id: UserID,
    limit: int,
    offset: int,
    sort_by: str = "created_at",
    sort_direction: str = "desc",
):
    """
    Получает список стратегий пользователя с статистикой бэктестов.

    Args:
        db: Асинхронная сессия БД
        user_id: UUID пользователя
        limit: Количество записей для возврата
        offset: Смещение от начала списка
        sort_by: Поле для сортировки
        sort_direction: Направление сортировки (asc/desc)

    Returns:
        Список объектов Row с данными стратегий и статистикой
    """
    # Подзапрос для подсчета всех бэктестов стратегии
    backtests_count_subq = (
        select(
            BacktestJobs.strategy_id,
            func.count().label("backtests_count"),
        )
        .group_by(BacktestJobs.strategy_id)
        .subquery()
    )

    # Подзапрос для получения последнего бэктеста с использованием ROW_NUMBER
    latest_backtest_cte = (
        select(
            BacktestJobs.strategy_id,
            BacktestJobs.id.label("last_backtest_id"),
            BacktestJobs.ticker.label("last_backtest_ticker"),
            BacktestJobs.created_at.label("last_backtest_created_at"),
            BacktestJobs.status.label("last_backtest_status"),
            BacktestResults.metrics["net_total_profit_pct"]
            .as_float()
            .label("last_backtest_net_total_profit_pct"),
            func.row_number()
            .over(
                partition_by=BacktestJobs.strategy_id,
                order_by=BacktestJobs.created_at.desc(),
            )
            .label("rn"),
        )
        .outerjoin(BacktestResults, BacktestJobs.id == BacktestResults.job_id)
        .subquery()
    )

    # Фильтруем только первую запись для каждой стратегии
    latest_backtest_subq = (
        select(
            latest_backtest_cte.c.strategy_id,
            latest_backtest_cte.c.last_backtest_id,
            latest_backtest_cte.c.last_backtest_ticker,
            latest_backtest_cte.c.last_backtest_created_at,
            latest_backtest_cte.c.last_backtest_status,
            latest_backtest_cte.c.last_backtest_net_total_profit_pct,
        )
        .where(latest_backtest_cte.c.rn == 1)
        .subquery()
    )

    # Основной запрос
    stmt = (
        select(
            Strategies,
            func.coalesce(backtests_count_subq.c.backtests_count, 0).label(
                "backtests_count"
            ),
            latest_backtest_subq.c.last_backtest_id,
            latest_backtest_subq.c.last_backtest_ticker,
            latest_backtest_subq.c.last_backtest_created_at,
            latest_backtest_subq.c.last_backtest_status,
            latest_backtest_subq.c.last_backtest_net_total_profit_pct,
        )
        .outerjoin(
            backtests_count_subq,
            Strategies.id == backtests_count_subq.c.strategy_id,
        )
        .outerjoin(
            latest_backtest_subq,
            Strategies.id == latest_backtest_subq.c.strategy_id,
        )
        .where(
            Strategies.user_id == user_id,
            ~Strategies.is_deleted,
        )
    )

    # Динамическая сортировка
    order_column = None
    if sort_by == "name":
        order_column = Strategies.name
    elif sort_by == "created_at":
        order_column = Strategies.created_at
    elif sort_by == "updated_at":
        order_column = Strategies.updated_at
    elif sort_by == "backtests_count":
        order_column = func.coalesce(backtests_count_subq.c.backtests_count, 0)
    else:
        order_column = Strategies.created_at

    if sort_direction.lower() == "asc":
        stmt = stmt.order_by(order_column.asc())
    else:
        stmt = stmt.order_by(order_column.desc())

    # Добавляем fallback сортировку
    if sort_by != "created_at":
        stmt = stmt.order_by(Strategies.created_at.desc())

    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.all()


async def get_strategies_count_by_user(
    db: AsyncSession, user_id: UserID
) -> int:
    """
    Считает общее количество стратегий пользователя.

    Args:
        db: Асинхронная сессия БД
        user_id: UUID пользователя

    Returns:
        Количество стратегий
    """
    stmt = select(func.count()).where(
        Strategies.user_id == user_id,
        ~Strategies.is_deleted,
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def update_strategy(
    db: AsyncSession,
    user_id: UserID,
    strategy_id: StrategyID,
    strategy_update: StrategyUpdateRequest,
):
    """
    Обновляет стратегию.

    Args:
        db: Асинхронная сессия БД
        user_id: UUID пользователя
        strategy_id: UUID стратегии
        strategy_update: Данные для обновления

    Returns:
        Обновленный объект Strategies или None если не найдена

    Raises:
        DuplicateNameError: Если стратегия с таким именем уже существует
    """
    # Lazy import для избежания циклической зависимости
    from app.services.strategy.indicator_key_validator import (
        IndicatorKeyValidator,
        normalize_strategy_definition,
    )

    # Проверяем уникальность названия (исключая текущую стратегию)
    name_exists = await check_strategy_name_exists(
        db,
        user_id=user_id,
        name=strategy_update.name,
        exclude_strategy_id=strategy_id,
    )
    if name_exists:
        raise DuplicateNameError("Strategy", strategy_update.name)

    # Получаем стратегию
    stmt = select(Strategies).where(
        Strategies.id == strategy_id,
        Strategies.user_id == user_id,
        ~Strategies.is_deleted,
    )
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()

    if not strategy:
        return None

    # Обновляем поля
    old_name = strategy.name
    strategy.name = strategy_update.name
    strategy.description = strategy_update.description

    # Нормализуем definition (убираем .0 из integer параметров)
    validator = IndicatorKeyValidator()
    strategy.definition = normalize_strategy_definition(
        strategy_update.definition.model_dump(), validator
    )
    strategy.updated_at = datetime.now(ZoneInfo("Europe/Moscow"))

    await db.flush()
    await db.refresh(strategy)

    log.info(
        "strategy.updated",
        strategy_id=str(strategy_id),
        user_id=str(user_id),
        old_name=old_name,
        new_name=strategy_update.name,
    )

    return strategy


async def delete_strategy(
    db: AsyncSession, user_id: UserID, strategy_id: StrategyID
) -> bool:
    """
    Мягко удаляет стратегию (soft delete).

    Args:
        db: Асинхронная сессия БД
        user_id: UUID пользователя
        strategy_id: UUID стратегии

    Returns:
        True если стратегия была удалена, False если не найдена
    """
    stmt = select(Strategies).where(
        Strategies.id == strategy_id,
        Strategies.user_id == user_id,
        ~Strategies.is_deleted,
    )
    result = await db.execute(stmt)
    strategy = result.scalar_one_or_none()

    if not strategy:
        return False

    strategy_name = strategy.name
    strategy.is_deleted = True
    await db.flush()

    log.info(
        "strategy.deleted",
        strategy_id=str(strategy_id),
        user_id=str(user_id),
        strategy_name=strategy_name,
    )

    return True


async def check_strategy_name_exists(
    db: AsyncSession,
    user_id: UserID,
    name: str,
    exclude_strategy_id: StrategyID | None = None,
) -> bool:
    """
    Проверяет существование стратегии с таким именем у пользователя.

    Args:
        db: Асинхронная сессия БД
        user_id: UUID пользователя
        name: Название стратегии
        exclude_strategy_id: UUID стратегии для исключения из проверки

    Returns:
        True если стратегия с таким именем существует, False иначе
    """
    stmt = select(func.count()).where(
        Strategies.user_id == user_id,
        Strategies.name == name,
        ~Strategies.is_deleted,
    )

    if exclude_strategy_id:
        stmt = stmt.where(Strategies.id != exclude_strategy_id)

    result = await db.execute(stmt)
    count = result.scalar_one()

    return count > 0
