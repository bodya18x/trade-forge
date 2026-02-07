"""
Модуль аутентификации и управления сессиями.

Содержит все эндпоинты для:
- Регистрации и входа (authentication)
- Управления токенами (tokens)
- Управления сессиями (sessions)
- CSRF защиты (csrf)
- Административных операций (admin)
"""

from __future__ import annotations

from fastapi import APIRouter

from .admin import router as admin_router
from .authentication import router as authentication_router
from .csrf import router as csrf_router
from .sessions import router as sessions_router
from .tokens import router as tokens_router

# Создаем главный роутер для всех auth endpoints
router = APIRouter()

# Подключаем все sub-routers
router.include_router(authentication_router, tags=["Authentication"])
router.include_router(tokens_router, tags=["Tokens"])
router.include_router(sessions_router, tags=["Sessions"])
router.include_router(csrf_router, tags=["CSRF Protection"])
router.include_router(admin_router, tags=["Admin"])

__all__ = ["router"]
