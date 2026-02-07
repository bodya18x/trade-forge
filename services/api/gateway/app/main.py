from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from tradeforge_db import close_db, init_db
from tradeforge_logger import configure_logging, get_logger
from tradeforge_logger.middleware import (
    LoggingMiddleware,
    RequestContextMiddleware,
)
from tradeforge_schemas import ErrorResponse

from app.api.v1.router import api_router
from app.core.proxy_client import internal_api_client
from app.core.rate_limiting import RateLimitingMiddleware
from app.core.redis import (
    close_redis_pools,
    get_rate_limit_redis,
    health_check_redis,
    init_redis_pools,
)
from app.core.security import (
    CSRFMiddleware,
    JWTSessionMiddleware,
    RequestSizeMiddleware,
    RequestTimingMiddleware,
    SecurityHeadersMiddleware,
)
from app.settings import settings

# Настраиваем логирование ДО создания приложения
configure_logging(
    service_name=settings.SERVICE_NAME,
    environment=settings.ENVIRONMENT,
    log_level=settings.LOG_LEVEL,
    version=settings.SERVICE_VERSION,
    enable_json=True,
)

# Получаем логгер для модуля
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управляет жизненным циклом приложения.
    """
    log.info("application.starting")

    # Инициализируем PostgreSQL через tradeforge_db
    init_db()
    log.info("database.postgresql.initialized")

    # Инициализируем пулы соединений Redis
    init_redis_pools()
    log.info("database.redis.pools.initialized")

    log.info("application.startup.complete")
    yield
    log.info("application.shutting.down")

    # Корректное закрытие
    await internal_api_client.close()
    await close_redis_pools()
    await close_db()
    log.info("database.connections.closed")

    log.info("application.shutdown.complete")


# Создаем экземпляр FastAPI приложения
app = FastAPI(
    title="Trade Forge - External API Gateway",
    description="Внешний API шлюз для безопасного доступа к Trade Forge платформе.",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Добавляем middleware безопасности
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(
    RequestSizeMiddleware, max_size=2 * 1024 * 1024
)  # Лимит 2MB

# Добавляем JWT Session Middleware для автоматической проверки сессий
app.add_middleware(JWTSessionMiddleware)

# Добавляем CSRF Middleware для защиты POST/PUT/DELETE операций
app.add_middleware(CSRFMiddleware)

# Добавляем Rate Limiting Middleware
# Инициализируется с get_rate_limit_redis для получения Redis
app.add_middleware(RateLimitingMiddleware, redis_getter=get_rate_limit_redis)

# Настраиваем middleware для observability
# Добавляем LoggingMiddleware для автоматического логирования запросов
app.add_middleware(
    LoggingMiddleware,
    skip_paths=[
        "/health",
        "/api/v1/openapi.json",
    ],  # Пропускаем служебные эндпоинты
)

# ВАЖНО: RequestContextMiddleware должен быть ПЕРВЫМ для корректной работы correlation_id
# (добавляется последним, так как middleware применяются в обратном порядке)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """
    Обработчик ошибок валидации Pydantic.
    """
    error_details = []
    for error in exc.errors():
        error_details.append(
            {
                "loc": list(map(str, error["loc"])),
                "msg": error["msg"],
                "type": error["type"],
            }
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            type="https://trade-forge.ru/errors/validation",
            title="Validation Error",
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="One or more fields failed validation.",
            instance=str(request.url),
            errors=error_details,
        ).model_dump(exclude_none=True),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Обработчик для FastAPI HTTPException для приведения их к нашему формату.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            type=f"https://trade-forge.ru/errors/{exc.status_code}",
            title="Request Error",
            status=exc.status_code,
            detail=exc.detail,
            instance=str(request.url),
        ).model_dump(exclude_none=True),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Обработчик для всех остальных необработанных исключений.
    """
    log.error(
        "error.unhandled",
        url=str(request.url),
        error_type=type(exc).__name__,
        error_message=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            type="https://trade-forge.ru/errors/internal-server-error",
            title="Internal Server Error",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred on the server.",
            instance=str(request.url),
        ).model_dump(exclude_none=True),
    )


# Подключение роутеров
app.include_router(api_router, prefix="/api/v1")


@app.get("/api/v1/openapi.json", include_in_schema=False)
async def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


@app.get("/api/v1/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/api/v1/openapi.json", title=f"{app.title} - Swagger UI"
    )


@app.get("/api/v1/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url="/api/v1/openapi.json", title=f"{app.title} - ReDoc"
    )


@app.get("/", tags=["Root"])
async def read_root():
    """Простой эндпоинт для проверки, что сервис запущен."""
    return {
        "message": f"Welcome to Trade Forge Gateway v{settings.SERVICE_VERSION}",
        "docs": "/api/v1/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check эндпоинт."""
    health_status = {"status": "healthy", "service": settings.SERVICE_NAME}

    # Проверяем соединения Redis
    try:
        redis_health = await health_check_redis()
        health_status["redis"] = redis_health

        # Если любой экземпляр Redis недоступен, отмечаем как degraded
        if not all(redis_health.values()):
            health_status["status"] = "degraded"

    except Exception as e:
        health_status["status"] = "degraded"
        health_status["redis"] = {"error": str(e)}

    return health_status
