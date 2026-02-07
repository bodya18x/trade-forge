"""
Модели и константы для работы со свечами MOEX.

Содержит Pydantic модели для валидации свечей и конфигурацию таймфреймов.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

# Константы timezone
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# Типы таймфреймов
TimeframeType = Literal["1min", "10min", "1h", "1d", "1w", "1m"]


# Конфигурация таймфреймов для MOEX API
TIMEFRAME_CONFIG: dict[str, dict[str, int]] = {
    "1min": {"interval": 1, "sleep": 60},
    "10min": {"interval": 10, "sleep": 600},
    "1h": {"interval": 60, "sleep": 3600},
    "1d": {"interval": 24, "sleep": 86400},
    "1w": {"interval": 7, "sleep": 604800},
    "1m": {"interval": 31, "sleep": 2678400},
}


class MoexCandle(BaseModel):
    """
    Pydantic-модель для валидации свечи с MOEX API.
    """

    model_config = ConfigDict(extra="ignore")

    open: float
    close: float
    high: float
    low: float
    volume: float
    begin: datetime

    ticker: str | None = None
    timeframe: str | None = None

    @field_validator("begin", mode="before")
    @classmethod
    def parse_datetime(cls, value: str | datetime) -> datetime:
        """
        Парсит строку времени от MOEX и присваивает московскую таймзону.

        Args:
            value: Строка в формате "YYYY-MM-DD HH:MM:SS" или datetime объект

        Returns:
            datetime с московской таймзоной
        """
        if isinstance(value, datetime):
            # Если уже datetime - убеждаемся что есть timezone
            if value.tzinfo is None:
                return value.replace(tzinfo=MOSCOW_TZ)
            return value.astimezone(MOSCOW_TZ)

        # Парсим строку
        naive_dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return naive_dt.replace(tzinfo=MOSCOW_TZ)

    @field_serializer("begin", when_used="json")
    def serialize_datetime(self, value: datetime) -> str:
        """
        Сериализует datetime в ISO формат при mode='json'.

        Args:
            value: datetime объект

        Returns:
            ISO строка
        """
        return value.isoformat()


def get_timeframe_interval(timeframe: str) -> int:
    """
    Получить значение interval для MOEX API по таймфрейму.

    Args:
        timeframe: Таймфрейм ('1h', '1d' и т.д.)

    Returns:
        Значение interval для MOEX API

    Raises:
        KeyError: Если таймфрейм не поддерживается
    """
    if timeframe not in TIMEFRAME_CONFIG:
        raise KeyError(
            f"Unsupported timeframe: {timeframe}. "
            f"Supported: {list(TIMEFRAME_CONFIG.keys())}"
        )
    return TIMEFRAME_CONFIG[timeframe]["interval"]
