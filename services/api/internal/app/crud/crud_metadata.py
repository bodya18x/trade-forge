"""
CRUD операции для работы с метаданными системы.

Этот модуль содержит функции для получения справочной информации:
системные индикаторы, рынки, тикеры.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import Markets, SystemIndicators, Tickers
from tradeforge_logger import get_logger

log = get_logger(__name__)


async def get_indicators(
    db: AsyncSession, limit: int, offset: int
) -> list[dict]:
    """
    Получает список всех активных системных индикаторов из справочника.

    Args:
        db: Асинхронная сессия базы данных
        limit: Максимальное количество результатов
        offset: Смещение для пагинации

    Returns:
        Список словарей с данными системных индикаторов
    """
    stmt = (
        select(
            SystemIndicators.name,
            SystemIndicators.display_name,
            SystemIndicators.description,
            SystemIndicators.category,
            SystemIndicators.complexity,
            SystemIndicators.parameters_schema,
            SystemIndicators.output_schema,
            SystemIndicators.key_template,
            SystemIndicators.is_enabled,
        )
        .where(SystemIndicators.is_enabled == True)
        .order_by(SystemIndicators.category, SystemIndicators.display_name)
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "name": row[0],
            "display_name": row[1],
            "description": row[2],
            "category": row[3],
            "complexity": row[4],
            "parameters_schema": row[5],
            "output_schema": row[6],
            "key_template": row[7],
            "is_enabled": row[8],
        }
        for row in rows
    ]


async def get_total_indicators_count(db: AsyncSession) -> int:
    """
    Получает общее количество активных системных индикаторов.

    Args:
        db: Асинхронная сессия базы данных

    Returns:
        Количество активных индикаторов
    """
    stmt = (
        select(func.count())
        .select_from(SystemIndicators)
        .where(SystemIndicators.is_enabled == True)
    )

    result = await db.execute(stmt)
    return result.scalar_one()


async def get_markets(db: AsyncSession) -> list[dict]:
    """
    Получает список всех рынков.

    Args:
        db: Асинхронная сессия базы данных

    Returns:
        Список словарей с данными рынков
    """
    stmt = select(Markets.market_code, Markets.description).order_by(
        Markets.market_code
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [{"market_code": row[0], "description": row[1]} for row in rows]


async def get_tickers(
    db: AsyncSession,
    limit: int,
    offset: int,
    market_code: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """
    Получает список тикеров с возможностью фильтрации по рынку и умным ранжированием поиска.

    Args:
        db: Асинхронная сессия базы данных
        limit: Максимальное количество результатов
        offset: Смещение для пагинации
        market_code: Опциональный код рынка для фильтрации
        search: Опциональная поисковая строка

    Returns:
        Список словарей с данными тикеров
    """
    # Базовый запрос
    stmt = select(
        Tickers.symbol,
        Tickers.market_id,
        Tickers.description,
        Tickers.type,
        Tickers.is_active,
        Tickers.lot_size,
        Tickers.min_step,
        Tickers.decimals,
        Tickers.isin,
        Tickers.currency,
    )

    # Добавляем JOIN если нужна фильтрация по рынку
    if market_code:
        stmt = stmt.join(Markets, Tickers.market_id == Markets.id).where(
            Markets.market_code == market_code
        )

    # Обработка поиска с умным ранжированием
    if search:
        search_upper = search.strip().upper()
        search_prefix = f"{search_upper}%"
        search_contains = f"%{search_upper}%"

        # Создаем CASE выражение для ранжирования
        search_rank = func.case(
            # Точное совпадение символа = максимальный приоритет
            (func.upper(Tickers.symbol) == search_upper, 1),
            # Символ начинается с поискового запроса
            (func.upper(Tickers.symbol).like(search_prefix), 2),
            # Описание начинается с поискового запроса
            (
                func.upper(func.coalesce(Tickers.description, "")).like(
                    search_prefix
                ),
                3,
            ),
            # Символ содержит поисковый запрос
            (func.upper(Tickers.symbol).like(search_contains), 4),
            # Описание содержит поисковый запрос
            (
                func.upper(func.coalesce(Tickers.description, "")).like(
                    search_contains
                ),
                5,
            ),
            else_=6,
        ).label("search_rank")

        stmt = stmt.add_columns(search_rank)

        # Условие поиска (символ или описание содержат запрос)
        stmt = stmt.where(
            or_(
                func.upper(Tickers.symbol).like(search_contains),
                func.upper(func.coalesce(Tickers.description, "")).like(
                    search_contains
                ),
            )
        )

        # Сортировка по релевантности, затем по алфавиту
        stmt = stmt.order_by(search_rank, Tickers.symbol)
    else:
        # Обычная сортировка без поиска
        stmt = stmt.order_by(Tickers.symbol)

    # Применяем пагинацию
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()

    # Если есть поиск, последний элемент - это search_rank, игнорируем его
    if search:
        return [
            {
                "symbol": row[0],
                "market_id": row[1],
                "description": row[2],
                "type": row[3].value,
                "is_active": row[4],
                "lot_size": row[5],
                "min_step": row[6],
                "decimals": row[7],
                "isin": row[8],
                "currency": row[9],
            }
            for row in rows
        ]
    else:
        return [
            {
                "symbol": row[0],
                "market_id": row[1],
                "description": row[2],
                "type": row[3].value,
                "is_active": row[4],
                "lot_size": row[5],
                "min_step": row[6],
                "decimals": row[7],
                "isin": row[8],
                "currency": row[9],
            }
            for row in rows
        ]


async def get_total_tickers_count(
    db: AsyncSession, market_code: str | None = None, search: str | None = None
) -> int:
    """
    Получает общее количество тикеров с фильтрацией по рынку и поиску.

    Args:
        db: Асинхронная сессия базы данных
        market_code: Опциональный код рынка для фильтрации
        search: Опциональная поисковая строка

    Returns:
        Общее количество тикеров
    """
    stmt = select(func.count()).select_from(Tickers)

    # Добавляем JOIN если нужна фильтрация по рынку
    if market_code:
        stmt = stmt.join(Markets, Tickers.market_id == Markets.id).where(
            Markets.market_code == market_code
        )

    # Добавляем поиск если указан
    if search:
        search_contains = f"%{search.strip().upper()}%"
        stmt = stmt.where(
            or_(
                func.upper(Tickers.symbol).like(search_contains),
                func.upper(func.coalesce(Tickers.description, "")).like(
                    search_contains
                ),
            )
        )

    result = await db.execute(stmt)
    return result.scalar_one()


async def get_popular_tickers(db: AsyncSession, limit: int = 30) -> list[dict]:
    """
    Получает список популярных тикеров (с list_level = 1).

    Args:
        db: Асинхронная сессия базы данных
        limit: Максимальное количество результатов (по умолчанию 30)

    Returns:
        Список словарей с данными популярных тикеров
    """
    stmt = (
        select(
            Tickers.symbol,
            Tickers.market_id,
            Tickers.description,
            Tickers.type,
            Tickers.is_active,
            Tickers.lot_size,
            Tickers.min_step,
            Tickers.decimals,
            Tickers.isin,
            Tickers.currency,
        )
        .where(Tickers.list_level == 1, Tickers.is_active == True)
        .order_by(Tickers.symbol)
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "symbol": row[0],
            "market_id": row[1],
            "description": row[2],
            "type": row[3].value,
            "is_active": row[4],
            "lot_size": row[5],
            "min_step": row[6],
            "decimals": row[7],
            "isin": row[8],
            "currency": row[9],
        }
        for row in rows
    ]


async def check_tickers_exist(
    db: AsyncSession, tickers: list[str]
) -> dict[str, bool]:
    """
    Проверяет существование и активность тикеров в системе.

    Args:
        db: Асинхронная сессия базы данных
        tickers: Список тикеров для проверки

    Returns:
        Словарь {ticker: exists_and_active}, где ключ - нормализованный тикер,
        значение - True если тикер существует и активен
    """
    if not tickers:
        return {}

    # Нормализуем тикеры (uppercase и strip)
    normalized_tickers = [ticker.strip().upper() for ticker in tickers]
    unique_tickers = list(set(normalized_tickers))

    # Получаем все существующие активные тикеры из списка
    stmt = select(Tickers.symbol).where(
        func.upper(Tickers.symbol).in_(unique_tickers),
        Tickers.is_active == True,
    )

    result = await db.execute(stmt)
    existing_tickers = {row[0].upper() for row in result.fetchall()}

    # Создаем результат для всех запрошенных тикеров
    return {ticker: ticker in existing_tickers for ticker in unique_tickers}
