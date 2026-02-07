from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from tradeforge_db import close_db, init_db
from tradeforge_logger import get_logger
from tradeforge_logger.middleware import (
    LoggingMiddleware,
    RequestContextMiddleware,
)
from tradeforge_schemas import ErrorResponse

from app.api.v1.router import api_router
from app.cache import close_redis_pool, init_redis_pool
from app.observability import setup_logging, setup_metrics, setup_tracing
from app.services.kafka_service import kafka_service
from app.settings import settings

# Настраиваем логирование ДО создания приложения
setup_logging()

# Получаем логгер для модуля
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управляет жизненным циклом приложения.
    """
    log.info("application.starting")
    init_db()
    await init_redis_pool()
    await kafka_service.start()  # Запуск AsyncKafkaProducer
    setup_tracing(app)
    log.info("application.startup.complete")
    yield
    log.info("application.shutting.down")
    await kafka_service.stop()  # Graceful shutdown с flush
    await close_redis_pool()
    await close_db()
    log.info("application.shutdown.complete")


# Создаем экземпляр FastAPI приложения
app = FastAPI(
    title="Trade Forge - Internal API",
    description="Внутренний сервис для оркестрации бизнес-логики платформы Trade Forge.",
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Настраиваем middleware для observability
app.add_middleware(
    LoggingMiddleware,
    skip_paths=[
        "/health",
        "/metrics",
        "/api/v1/openapi.json",
    ],  # Пропускаем служебные эндпоинты
)

# ВАЖНО: RequestContextMiddleware должен быть ПЕРВЫМ для корректной работы correlation_id
# (добавляется последним, так как middleware применяются в обратном порядке)
app.add_middleware(RequestContextMiddleware)

# Настраиваем метрики Prometheus
setup_metrics(app)


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


# --- Подключение Роутеров ---
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
    # Здесь можно модифицировать схему, если потребуется
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
        "message": f"Welcome to Trade Forge Internal API v{settings.SERVICE_VERSION}"
    }
