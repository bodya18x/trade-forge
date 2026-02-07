from fastapi import APIRouter

from app.api.v1.endpoints import backtests, metadata, strategies, system

# Главный роутер для API v1
api_router = APIRouter()

# Подключаем роутеры из модулей
api_router.include_router(
    system.router, prefix="/system", tags=["System & Health"]
)
api_router.include_router(
    metadata.router, prefix="/metadata", tags=["Metadata & Dictionaries"]
)
api_router.include_router(
    strategies.router, prefix="/strategies", tags=["Strategies"]
)
api_router.include_router(
    backtests.router, prefix="/backtests", tags=["Backtests"]
)
