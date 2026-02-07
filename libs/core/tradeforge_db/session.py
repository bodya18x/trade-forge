"""
Управление соединениями с PostgreSQL.

Предоставляет DatabaseManager для управления пулом соединений
и фабрику для создания асинхронных сессий.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import DatabaseSettings


class DatabaseManager:
    """
    Менеджер подключений к PostgreSQL.

    Управляет пулом соединений и предоставляет фабрику для создания сессий.

    Attributes:
        engine: Асинхронный движок SQLAlchemy
        async_session_maker: Фабрика для создания асинхронных сессий
    """

    def __init__(
        self,
        database_url: str,
        *,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_pre_ping: bool = True,
        echo: bool = False,
    ):
        """
        Инициализирует менеджер БД.

        Args:
            database_url: DSN строка для подключения (postgresql+asyncpg://...)
            pool_size: Размер пула соединений
            max_overflow: Максимальное количество дополнительных соединений
            pool_pre_ping: Проверять соединение перед использованием
            echo: Выводить SQL запросы в логи
        """
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=echo,
            pool_pre_ping=pool_pre_ping,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self.async_session_maker: async_sessionmaker[AsyncSession] = (
            async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager для получения сессии БД.

        Автоматически выполняет commit при успехе и rollback при ошибке.

        Yields:
            AsyncSession: Асинхронная сессия SQLAlchemy

        Example:
            ```python
            db_manager = DatabaseManager(settings.POSTGRES_URL)

            async with db_manager.session() as session:
                user = await session.execute(select(Users).where(Users.id == user_id))
                # session.commit() будет вызван автоматически
            ```
        """
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def close(self) -> None:
        """
        Закрывает все соединения в пуле.

        Следует вызывать при остановке приложения.
        """
        await self.engine.dispose()


# Глобальный инстанс менеджера БД (опционально для использования в сервисах)
_db_manager: DatabaseManager | None = None


def init_db(settings: DatabaseSettings | None = None) -> DatabaseManager:
    """
    Инициализирует глобальный DatabaseManager.

    Args:
        settings: Настройки подключения к БД. Если None, загружаются из окружения.

    Returns:
        DatabaseManager: Инициализированный менеджер БД

    Example:
        ```python
        from tradeforge_db.config import DatabaseSettings
        from tradeforge_db.session import init_db

        settings = DatabaseSettings()
        db_manager = init_db(settings)
        ```
    """
    global _db_manager

    if settings is None:
        settings = DatabaseSettings()

    _db_manager = DatabaseManager(
        database_url=settings.POSTGRES_URL,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_pre_ping=settings.POSTGRES_POOL_PRE_PING,
        echo=settings.POSTGRES_ECHO,
    )
    return _db_manager


def get_db_manager() -> DatabaseManager:
    """
    Получает глобальный DatabaseManager.

    Returns:
        DatabaseManager: Инстанс менеджера БД

    Raises:
        RuntimeError: Если менеджер не был инициализирован через init_db()

    Example:
        ```python
        from tradeforge_db.session import get_db_manager

        db_manager = get_db_manager()
        async with db_manager.session() as session:
            ...
        ```
    """
    if _db_manager is None:
        raise RuntimeError(
            "Database manager not initialized. Call init_db() first."
        )
    return _db_manager


async def close_db() -> None:
    """
    Закрывает глобальный DatabaseManager.

    Следует вызывать при остановке приложения.

    Example:
        ```python
        from tradeforge_db.session import close_db

        # При shutdown приложения
        await close_db()
        ```
    """
    if _db_manager is not None:
        await _db_manager.close()
