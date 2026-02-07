from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Централизованная конфигурация для сервиса Gateway API.
    Загружает переменные из глобального platform/.env и локального .env файлов.
    """

    model_config = SettingsConfigDict(
        env_file=[
            "../../../platform/.env",
            ".env",
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Общие настройки сервиса ---
    SERVICE_NAME: str = Field("trade-forge-gateway", description="Имя сервиса")
    SERVICE_VERSION: str = Field("0.2.0", description="Версия сервиса")
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        "development", description="Окружение"
    )
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        Field("INFO", description="Уровень логирования")
    )

    # --- JWT настройки ---
    JWT_SECRET_KEY: str = Field(
        "your_jwt_secret_key_change_this_in_production_please",
        description="JWT секретный ключ",
    )
    JWT_ALGORITHM: str = Field("HS256", description="JWT алгоритм")
    JWT_EXPIRE_MINUTES: int = Field(
        15, description="JWT access token время жизни в минутах"
    )  # 15 минут для access token
    JWT_REFRESH_EXPIRE_DAYS: int = Field(
        30, description="JWT refresh token время жизни в днях"
    )  # 30 дней для refresh token

    # --- Redis (используем компоненты из platform/.env) ---
    REDIS_HOST: str = Field("localhost", description="Redis host")
    REDIS_PORT: int = Field(26379, description="Redis port")
    REDIS_PASSWORD: str = Field(
        "strong_password", description="Redis password"
    )
    REDIS_DB: int = Field(1, description="Redis database number для Gateway")

    @computed_field
    @property
    def REDIS_DSN(self) -> str:
        """Строит DSN для Redis из компонентов."""
        return (
            f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:"
            f"{self.REDIS_PORT}/{self.REDIS_DB}"
        )

    # --- Internal API ---
    INTERNAL_API_BASE_URL: str = Field(
        "http://internal-api:8000", description="Base URL внутреннего API"
    )
    INTERNAL_API_TIMEOUT: int = Field(
        30, description="Таймаут для запросов к внутреннему API в секундах"
    )

    # --- CORS настройки ---
    CORS_ORIGINS: list[str] = Field(
        ["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Разрешенные CORS origins",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        True, description="Разрешить CORS credentials"
    )
    CORS_ALLOW_METHODS: list[str] = Field(
        ["*"], description="Разрешенные HTTP методы"
    )
    CORS_ALLOW_HEADERS: list[str] = Field(
        ["*"], description="Разрешенные HTTP заголовки"
    )

    # --- Rate Limiting Settings ---
    # Базовые IP-лимиты (применяются глобально)
    RATE_LIMIT_IP_AUTH_PER_SECOND: int = Field(
        2, description="IP-based requests per second for auth endpoints"
    )
    RATE_LIMIT_IP_GENERAL_PER_SECOND: int = Field(
        10, description="IP-based requests per second for general endpoints"
    )
    RATE_LIMIT_IP_REGISTER_PER_HOUR: int = Field(
        10, description="Registration attempts per hour per IP"
    )
    RATE_LIMIT_IP_LOGIN_PER_HOUR: int = Field(
        20, description="Login attempts per hour per IP"
    )

    # GeoIP
    GEOIP_DATABASE_PATH: str = Field(
        "", description="Путь к файлу с базой городов GeoIP"
    )

    # Rate limiting использует тот же Redis что и основной (упрощенная конфигурация)
    @computed_field
    @property
    def RATE_LIMIT_REDIS_DSN(self) -> str:
        """Строит DSN для Rate Limiting Redis - используем тот же что и основной."""
        return self.REDIS_DSN

    # --- Subscription Tiers and Limits ---
    # Все пользовательские лимиты централизованы в подписках
    SUBSCRIPTION_LIMITS: dict[str, dict[str, int]] = {
        "free": {
            # Ресурсные лимиты
            "strategies_per_day": 5,
            "backtests_per_day": 25,
            "concurrent_backtests": 2,
            "backtest_max_years": 1,
            # Пользовательские rate limits
            "user_general_per_hour": 1000,
            "user_write_per_hour": 100,
        },
        "pro": {
            # Ресурсные лимиты
            "strategies_per_day": 50,
            "backtests_per_day": 200,
            "concurrent_backtests": 10,
            "backtest_max_years": 5,
            # Пользовательские rate limits
            "user_general_per_hour": 2000,
            "user_write_per_hour": 400,
        },
        "enterprise": {
            # Ресурсные лимиты
            "strategies_per_day": 500,
            "backtests_per_day": 1000,
            "concurrent_backtests": 50,
            "backtest_max_years": 10,
            # Пользовательские rate limits
            "user_general_per_hour": 5000,
            "user_write_per_hour": 1000,
        },
    }


# Используем lru_cache для создания синглтона
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
