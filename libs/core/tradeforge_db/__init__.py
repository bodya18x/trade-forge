"""
Trade Forge Database Library.

Библиотека для работы с PostgreSQL в проекте Trade Forge.
"""

from __future__ import annotations

# Configuration
from .config import DatabaseSettings

# FastAPI dependencies
from .dependencies import get_db_session

# Реэкспорт всех моделей из подмодуля models
# Это избегает дублирования импортов между models/__init__.py и этим файлом
from .models import *  # noqa: F403, F401

# Session management
from .session import DatabaseManager, close_db, get_db_manager, init_db


# Импортируем __all__ из models и дополняем своими экспортами
from .models import __all__ as _models_all

__all__ = [
    # Configuration
    "DatabaseSettings",
    # Session management
    "DatabaseManager",
    "init_db",
    "get_db_manager",
    "close_db",
    # Dependencies
    "get_db_session",
    # Добавляем все модели из models/__init__.py
    *_models_all,
]
