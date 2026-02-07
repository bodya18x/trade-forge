"""
Базовые модели для работы со свечами.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BaseCandle(BaseModel):
    """Базовая модель свечи с основными параметрами."""

    ticker: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    value: Optional[float] = None
    begin: datetime
    end: datetime
