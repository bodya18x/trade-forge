"""
Обработчики задач для collection consumer.

Обработчики выполняют различные типы задач по сбору данных.
"""

from __future__ import annotations

from .candles import create_candles_handler

__all__ = ["create_candles_handler"]
