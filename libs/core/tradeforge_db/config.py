"""
Настройки подключения к PostgreSQL для Trade Forge.

Загружает конфигурацию из переменных окружения.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """
    Настройки подключения к PostgreSQL.

    Все параметры загружаются из переменных окружения с префиксом POSTGRES_.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- PostgreSQL Connection ---
    POSTGRES_HOST: Annotated[
        str, Field(..., description="Хост базы данных PostgreSQL")
    ]
    POSTGRES_PORT: Annotated[
        int, Field(5432, description="Порт базы данных PostgreSQL")
    ]
    POSTGRES_DB: Annotated[
        str, Field(..., description="Имя базы данных в PostgreSQL")
    ]
    POSTGRES_USER: Annotated[
        str,
        Field(..., description="Пользователь для подключения к PostgreSQL"),
    ]
    POSTGRES_PASSWORD: Annotated[
        str, Field(..., description="Пароль для подключения к PostgreSQL")
    ]

    # --- Connection Pool Settings ---
    POSTGRES_POOL_SIZE: Annotated[
        int,
        Field(10, description="Размер пула соединений"),
    ]
    POSTGRES_MAX_OVERFLOW: Annotated[
        int,
        Field(
            20, description="Максимальное количество дополнительных соединений"
        ),
    ]
    POSTGRES_POOL_PRE_PING: Annotated[
        bool,
        Field(
            True,
            description="Проверять соединение перед использованием из пула",
        ),
    ]
    POSTGRES_ECHO: Annotated[
        bool,
        Field(False, description="Выводить SQL запросы в логи"),
    ]

    @computed_field(return_type=str)
    @property
    def POSTGRES_URL(self) -> str:
        """
        Полный URL для подключения к PostgreSQL (asyncpg драйвер).

        Returns:
            DSN строка в формате postgresql+asyncpg://user:password@host:port/database
        """
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
