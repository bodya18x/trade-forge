from __future__ import annotations

import time
import uuid

from fastapi import Request, status
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from tradeforge_db import get_db_session
from tradeforge_logger import get_logger
from tradeforge_schemas import ErrorResponse

from app.core.auth import extract_token_data
from app.core.redis import get_main_redis
from app.settings import settings

log = get_logger(__name__)

# Настройка для хеширования паролей с bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Хеширует пароль с использованием bcrypt.

    Args:
        password: Открытый пароль для хеширования

    Returns:
        Захешированный пароль
    """
    # Bcrypt имеет лимит в 72 байта для пароля
    # Обрезаем пароль, если он длиннее
    if isinstance(password, str):
        password_bytes = password.encode("utf-8")
        if len(password_bytes) > 72:
            password = password_bytes[:72].decode("utf-8", errors="ignore")

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие открытого пароля хешированному.

    Args:
        plain_password: Открытый пароль
        hashed_password: Захешированный пароль для проверки

    Returns:
        True если пароль правильный, False иначе
    """
    # Bcrypt имеет лимит в 72 байта для пароля
    # Обрезаем пароль, если он длиннее
    if isinstance(plain_password, str):
        plain_password_bytes = plain_password.encode("utf-8")
        if len(plain_password_bytes) > 72:
            plain_password = plain_password_bytes[:72].decode(
                "utf-8", errors="ignore"
            )

    return pwd_context.verify(plain_password, hashed_password)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware для добавления заголовков безопасности ко всем ответам.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Добавляем заголовки безопасности
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        # Добавляем HSTS только в продакшене
        if settings.LOG_LEVEL != "DEBUG":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # Убираем заголовок server для безопасности
        if "server" in response.headers:
            del response.headers["server"]

        return response


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """
    Middleware для ограничения размера запросов во избежание DoS атак.
    """

    def __init__(self, app, max_size: int = 1024 * 1024):  # По умолчанию 1MB
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        # Проверяем заголовок Content-Length
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_size:
                    log.warning(
                        "request.size.too.large",
                        content_length=size,
                        max_size=self.max_size,
                        client_ip=(
                            request.client.host
                            if request.client
                            else "unknown"
                        ),
                    )

                    error_response = ErrorResponse(
                        type="https://trade-forge.ru/errors/request-too-large",
                        title="Request Too Large",
                        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Request size {size} exceeds maximum allowed size of {self.max_size} bytes",
                        instance=str(request.url),
                    )

                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content=error_response.model_dump(exclude_none=True),
                    )
            except ValueError:
                # Некорректный заголовок Content-Length
                pass

        return await call_next(request)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для добавления таймингов запросов и логирования для мониторинга.
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)

        # Логируем медленные запросы
        if process_time > 1.0:  # Логируем запросы, занимающие более 1 секунды
            log.warning(
                "request.slow.detected",
                method=request.method,
                path=request.url.path,
                process_time=process_time,
                status_code=response.status_code,
                client_ip=request.client.host if request.client else "unknown",
            )

        return response


class JWTSessionMiddleware(BaseHTTPMiddleware):
    """
    JWT Session Middleware для проверки session_id и обновления last_activity.

    Функциональность:
    - Извлекает session_id из JWT токена на каждом аутентифицированном запросе
    - Проверяет существование сессии в БД
    - Обновляет last_activity сессии
    - Блокирует запросы с недействительными сессиями
    """

    def __init__(self, app, excluded_paths: list[str] = None):
        """
        Инициализация middleware.

        Args:
            app: FastAPI приложение
            excluded_paths: Список путей, которые нужно исключить из проверки
        """
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/api/v1/docs",
            "/api/v1/openapi.json",
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/login-extended",
            "/api/v1/auth/refresh",
            "/api/v1/auth/refresh-extended",
            "/health",
            "/metrics",
        ]

    async def dispatch(self, request: Request, call_next):
        """Обработка каждого запроса."""

        # Пропускаем исключенные пути
        if any(
            request.url.path.startswith(path) for path in self.excluded_paths
        ):
            return await call_next(request)

        # Проверяем наличие Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # Нет токена - пропускаем (dependency functions обработают)
            return await call_next(request)

        # Извлекаем токен
        token = auth_header.split(" ", 1)[1]

        try:
            # Извлекаем данные токена
            token_data = await extract_token_data(token)
            if not token_data:
                return await self._create_auth_error(
                    "Invalid or expired token"
                )

            session_id = token_data["session_id"]

            # Получаем DB сессию
            async for db in get_db_session():
                # Проверяем и обновляем сессию
                session_valid = await self._validate_and_update_session(
                    db, session_id, token_data["user_id"]
                )

                if not session_valid:
                    return await self._create_auth_error(
                        "Session not found or expired"
                    )

                break

            # Добавляем session_id в request state для использования в endpoints
            request.state.session_id = session_id

            return await call_next(request)

        except Exception as e:
            log.error(
                "jwt.session.middleware.error",
                error=str(e),
                path=request.url.path,
                method=request.method,
            )
            return await self._create_auth_error("Authentication error")

    async def _validate_and_update_session(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """
        Проверяет существование сессии и обновляет last_activity.

        Args:
            db: Сессия базы данных
            session_id: ID сессии
            user_id: ID пользователя

        Returns:
            True если сессия валидна и обновлена, False иначе
        """
        try:
            from app.crud.crud_sessions import update_session_activity

            # Обновляем last_activity сессии
            success = await update_session_activity(
                db=db, session_id=session_id, user_id=user_id
            )

            return success

        except Exception as e:
            log.error(
                "session.validate.update.failed",
                session_id=str(session_id),
                user_id=str(user_id),
                error=str(e),
            )
            return False

    async def _create_auth_error(self, detail: str) -> JSONResponse:
        """
        Создает стандартизированный ответ об ошибке аутентификации.

        Args:
            detail: Детали ошибки

        Returns:
            JSONResponse с ошибкой 401
        """
        error_response = ErrorResponse(
            type="https://trade-forge.ru/errors/authentication-failed",
            title="Authentication Failed",
            status=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            instance="session-validation",
        )

        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=error_response.model_dump(exclude_none=True),
            headers={"WWW-Authenticate": "Bearer"},
        )


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF Middleware для автоматической защиты POST/PUT/DELETE операций.

    Функциональность:
    - Проверяет CSRF токены на всех POST/PUT/DELETE запросах с активной сессией
    - Извлекает токен из заголовка X-CSRF-Token
    - Сравнивает с сохраненным в Redis токеном для сессии
    - Блокирует запросы с неверными/отсутствующими токенами
    """

    def __init__(self, app, excluded_paths: list[str] = None):
        """
        Инициализация CSRF middleware.

        Args:
            app: FastAPI приложение
            excluded_paths: Список путей, которые нужно исключить из проверки
        """
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/api/v1/docs",
            "/api/v1/openapi.json",
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/csrf-token",
            "/health",
            "/metrics",
        ]
        # Методы, требующие CSRF защиты
        self.protected_methods = {"POST", "PUT", "DELETE", "PATCH"}

    async def dispatch(self, request: Request, call_next):
        """Обработка каждого запроса."""

        # Пропускаем исключенные пути
        if any(
            request.url.path.startswith(path) for path in self.excluded_paths
        ):
            return await call_next(request)

        # Пропускаем методы, не требующие CSRF защиты
        if request.method not in self.protected_methods:
            return await call_next(request)

        # Проверяем наличие Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # Нет токена - пропускаем (другие middleware обработают)
            return await call_next(request)

        # Извлекаем токен и данные
        token = auth_header.split(" ", 1)[1]

        try:
            # Извлекаем данные токена
            token_data = await extract_token_data(token)
            if not token_data:
                return await call_next(
                    request
                )  # Невалидный токен - пропускаем

            session_id = token_data["session_id"]

            # Извлекаем CSRF токен из заголовка
            csrf_token = request.headers.get("X-CSRF-Token")
            if not csrf_token:
                return await self._create_csrf_error(
                    "CSRF token is required for this operation"
                )

            # Проверяем CSRF токен в Redis
            is_valid = await self._validate_csrf_token(session_id, csrf_token)
            if not is_valid:
                return await self._create_csrf_error(
                    "Invalid or expired CSRF token"
                )

            return await call_next(request)

        except Exception as e:
            log.error(
                "csrf.middleware.error",
                error=str(e),
                path=request.url.path,
                method=request.method,
            )
            return await self._create_csrf_error("CSRF validation error")

    async def _validate_csrf_token(
        self, session_id: uuid.UUID, csrf_token: str
    ) -> bool:
        """
        Проверяет CSRF токен в Redis.

        Args:
            session_id: ID сессии
            csrf_token: CSRF токен для проверки

        Returns:
            True если токен валиден, False иначе
        """
        try:
            redis = get_main_redis()
            if not redis:
                log.error("csrf.redis.unavailable")
                return False

            # Ключ для CSRF токена в Redis
            csrf_key = f"csrf_token:{session_id}"

            # Получаем сохраненный токен
            stored_token = await redis.get(csrf_key)
            if not stored_token:
                return False

            # Сравниваем токены (stored_token уже строка из-за decode_responses=True)
            result = stored_token == csrf_token

            return result

        except Exception as e:
            log.error(
                "csrf.token.validation.failed",
                session_id=str(session_id),
                error=str(e),
            )
            return False

    async def _create_csrf_error(self, detail: str) -> JSONResponse:
        """
        Создает стандартизированный ответ об ошибке CSRF.

        Args:
            detail: Детали ошибки

        Returns:
            JSONResponse с ошибкой 403
        """
        error_response = ErrorResponse(
            type="https://trade-forge.ru/errors/csrf-validation-failed",
            title="CSRF Validation Failed",
            status=status.HTTP_403_FORBIDDEN,
            detail=detail,
            instance="csrf-validation",
        )

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error_response.model_dump(exclude_none=True),
        )
