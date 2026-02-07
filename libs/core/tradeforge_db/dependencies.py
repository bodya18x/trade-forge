"""
FastAPI dependencies для работы с PostgreSQL.

Предоставляет dependency injection для получения сессий БД в эндпоинтах.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from .session import get_db_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency для получения сессии БД.

    Автоматически управляет транзакциями (commit/rollback) и закрывает сессию.

    Yields:
        AsyncSession: Асинхронная сессия SQLAlchemy

    Example:
        ```python
        from fastapi import APIRouter, Depends
        from sqlalchemy.ext.asyncio import AsyncSession
        from tradeforge_db.dependencies import get_db_session
        from tradeforge_db.models import Users

        router = APIRouter()

        @router.get("/users/{user_id}")
        async def get_user(
            user_id: UUID,
            db: AsyncSession = Depends(get_db_session)
        ):
            result = await db.execute(
                select(Users).where(Users.id == user_id)
            )
            user = result.scalar_one_or_none()
            return user
        ```
    """
    db_manager = get_db_manager()
    async with db_manager.session() as session:
        yield session
