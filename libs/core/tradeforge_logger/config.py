# -*- coding: utf-8 -*-
"""Конфигурация для трейдфорж логгера.

Этот модуль содержит Pydantic-based конфигурацию для системы логирования.
"""

from __future__ import annotations

import socket
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Предопределенный список чувствительных полей для sanitization
DEFAULT_SENSITIVE_FIELDS = [
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "auth",
    "bearer",
    "access_token",
    "refresh_token",
    "credit_card",
    "card_number",
    "cvv",
    "cvc",
    "ssn",
    "passport",
    "private_key",
    "secret_key",
]

# Валидные уровни логирования
LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LoggerConfig(BaseSettings):
    """Конфигурация для системы логирования Trade Forge.

    Attributes:
        service_name: Имя микросервиса (обязательно).
        version: Версия сервиса.
        environment: Окружение (development, staging, production).
        log_level: Уровень логирования.
        enable_json: Использовать JSON формат для логов.
        enable_console_colors: Включить цветной вывод в консоли.
        sanitize_fields: Список полей для маскировки в логах.
        additional_context: Дополнительные поля для всех логов.
        enable_tracing: Включить интеграцию с OpenTelemetry.
        host: Имя хоста (автоматически определяется).
        add_caller_info: Добавлять информацию о файле и строке.
    """

    model_config = SettingsConfigDict(
        env_prefix="TRADEFORGE_LOG_",
        case_sensitive=False,
        frozen=True,  # Immutable конфигурация
    )

    # Обязательные поля
    service_name: str = Field(
        ...,
        description="Имя микросервиса",
        min_length=1,
    )

    # Метаданные сервиса
    version: str = Field(
        default="unknown",
        description="Версия сервиса",
    )
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Окружение выполнения",
    )

    # Настройки логирования
    log_level: str = Field(
        default="INFO",
        description="Уровень логирования",
    )
    enable_json: bool = Field(
        default=True,
        description="Использовать JSON формат (рекомендуется для production)",
    )
    enable_console_colors: bool = Field(
        default=False,
        description="Цветной вывод в консоли (только для development)",
    )

    # Безопасность
    sanitize_fields: list[str] = Field(
        default_factory=lambda: DEFAULT_SENSITIVE_FIELDS.copy(),
        description="Список полей для маскировки",
    )

    # Контекст
    additional_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные поля для всех логов",
    )

    # Интеграции
    enable_tracing: bool = Field(
        default=False,
        description="Включить интеграцию с OpenTelemetry",
    )

    # Системная информация
    host: str = Field(
        default_factory=lambda: socket.gethostname(),
        description="Имя хоста",
    )

    # Дополнительные опции
    add_caller_info: bool = Field(
        default=False,
        description="Добавлять информацию о файле и строке (замедляет работу)",
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Валидация уровня логирования.

        Args:
            v: Уровень логирования.

        Returns:
            Валидированный уровень логирования в верхнем регистре.

        Raises:
            ValueError: Если уровень логирования невалиден.
        """
        v_upper = v.upper()
        if v_upper not in LOG_LEVELS:
            raise ValueError(
                f"Invalid log level: {v}. Must be one of {LOG_LEVELS}"
            )
        return v_upper

    @field_validator("sanitize_fields")
    @classmethod
    def validate_sanitize_fields(cls, v: list[str]) -> list[str]:
        """Нормализация списка чувствительных полей.

        Args:
            v: Список полей.

        Returns:
            Нормализованный список (lowercase).
        """
        return [field.lower() for field in v]
