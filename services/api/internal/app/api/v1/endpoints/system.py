from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session

from app.cache import get_redis_client
from app.settings import settings

router = APIRouter()


@router.get("/health/live", summary="Liveness Probe")
async def liveness_check():
    """
    Проверяет, что сервис запущен и отвечает.
    """
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness Probe")
async def readiness_check(
    db: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client),
):
    """
    Проверяет готовность сервиса к приему трафика (доступность зависимостей).
    """
    # 1. Проверка подключения к PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Database connection failed: {e}"
        )

    # 2. Проверка подключения к Redis
    try:
        await redis.ping()
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Redis connection failed: {e}"
        )

    return {"status": "ready"}


@router.get("/version", summary="Get Service Version")
async def get_version():
    """Возвращает текущую версию сервиса."""
    return {"version": settings.SERVICE_VERSION}
