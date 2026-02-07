from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import auth, backtests, metadata, profile, strategies

# Главный роутер для API v1
api_router = APIRouter()

# Публичные маршруты (без аутентификации)
# Auth роутер теперь модульный - содержит sub-routers для authentication, tokens, sessions, csrf, admin
api_router.include_router(auth.router, prefix="/auth")

# Защищенные маршруты (требуют JWT токен)
api_router.include_router(
    profile.router, prefix="/profile", tags=["User Profile"]
)

# Business Logic маршруты с валидацией и rate limiting (требуют JWT токен)
api_router.include_router(
    strategies.router, prefix="/strategies", tags=["Strategies"]
)
api_router.include_router(
    backtests.router, prefix="/backtests", tags=["Backtests"]
)
api_router.include_router(
    metadata.router, prefix="/metadata", tags=["Metadata"]
)
