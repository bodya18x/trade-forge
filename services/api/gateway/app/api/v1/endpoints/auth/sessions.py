"""
Эндпоинты управления сессиями - Просмотр и завершение сессий.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import get_db_session
from tradeforge_logger import get_logger

from app.crud.crud_sessions import (
    cleanup_expired_sessions,
    get_user_sessions,
    log_security_event,
    terminate_all_user_sessions,
    terminate_session,
)
from app.dependencies import get_current_user, get_current_user_with_session
from app.schemas.auth import (
    CurrentUserInfo,
    DeviceInfo,
    SessionInfo,
    SessionsListResponse,
    TerminateAllSessionsRequest,
    TerminateAllSessionsResponse,
    TerminateSessionResponse,
)

log = get_logger(__name__)

router = APIRouter()


@router.get(
    "/sessions",
    response_model=SessionsListResponse,
    summary="Получить список активных сессий",
    description="""
    Возвращает список всех активных сессий пользователя.

    **Функциональность:**
    - Показывает все активные сессии пользователя
    - Включает информацию об устройствах и IP адресах
    - Помечает текущую сессию
    - Автоматически очищает истекшие сессии
    - Показывает геолокацию (опционально)

    **Информация о сессии:**
    - ID сессии
    - Информация об устройстве (тип, название, User-Agent)
    - IP адрес и геолокация
    - Время создания и последней активности
    - Время истечения

    **Use case:**
    Пользователь может увидеть все свои устройства, как в Google или Apple аккаунтах.
    """,
)
async def get_user_sessions_api(
    current_user: Annotated[
        "CurrentUserInfo", Depends(get_current_user_with_session)
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Получает список всех активных сессий пользователя.

    - Извлекает user_id из JWT токена
    - Получает все активные сессии из БД
    - Помечает текущую сессию по session_id
    - Очищает истекшие сессии
    """

    user_id = current_user.id
    current_session_id = current_user.session_id

    # Очищаем истекшие сессии
    await cleanup_expired_sessions(db)

    # Получаем активные сессии
    sessions = await get_user_sessions(
        db=db, user_id=user_id, current_session_id=current_session_id
    )

    # Преобразуем в нужный формат
    session_list = []
    for session in sessions:
        device_info_dict = session["device_info"]

        session_info = SessionInfo(
            session_id=session["session_id"],
            device_info=(
                DeviceInfo(**device_info_dict)
                if device_info_dict
                else DeviceInfo()
            ),
            created_at=session["created_at"],
            last_activity=session["last_activity"],
            is_current=session["is_current"],
            expires_at=session["expires_at"],
        )
        session_list.append(session_info)

    log.info(
        "user.sessions.retrieved",
        user_id=str(user_id),
        total_sessions=len(session_list),
    )

    return SessionsListResponse(
        sessions=session_list, total_sessions=len(session_list)
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=TerminateSessionResponse,
    summary="Завершить конкретную сессию",
    description="""
    Завершает конкретную сессию пользователя по её ID.

    **Функциональность:**
    - Проверяет принадлежность сессии текущему пользователю
    - Добавляет refresh токены сессии в blacklist
    - Удаляет сессию из БД
    - Логирует принудительное завершение

    **Безопасность:**
    - Можно завершать только свои сессии
    - Автоматическая инвалидация всех токенов сессии
    - Полное логирование для аудита

    **Use case:**
    Пользователь увидел подозрительную активность на одном устройстве
    и хочет завершить только эту сессию.
    """,
)
async def terminate_user_session(
    session_id: uuid.UUID,
    current_user: Annotated["CurrentUserInfo", Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Завершает конкретную сессию пользователя.

    - Проверяет принадлежность сессии пользователю
    - Завершает сессию в БД
    - Логирует событие принудительного завершения
    """

    user_id = current_user.id

    # Завершаем сессию
    success = await terminate_session(
        db=db, session_id=session_id, user_id=user_id
    )

    if not success:
        log.warning(
            "session.termination.nonexistent",
            user_id=str(user_id),
            session_id=str(session_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or does not belong to user",
        )

    # Логируем принудительное завершение
    await log_security_event(
        db=db,
        event_type="session_terminated_manually",
        user_id=user_id,
        session_id=session_id,
        details={
            "reason": "user_terminated",
            "terminated_session_id": str(session_id),
        },
    )

    log.info(
        "session.terminated.manually",
        user_id=str(user_id),
        terminated_session_id=str(session_id),
    )

    return TerminateSessionResponse(
        message="Session terminated successfully",
        success=True,
        session_id=session_id,
    )


@router.delete(
    "/sessions",
    response_model=TerminateAllSessionsResponse,
    summary="Завершить все сессии кроме текущей",
    description="""
    Завершает все сессии пользователя, кроме текущей (опционально).

    **Функциональность:**
    - Завершает все или почти все сессии одним запросом
    - Опция `keep_current` для сохранения текущей сессии
    - Добавляет все refresh токены в blacklist
    - Логирует массовое завершение сессий

    **Use case:**
    - Подозрение на компрометацию аккаунта
    - Смена пароля (завершить все сессии)
    - Общая "очистка" сессий для безопасности

    **Пример использования:**
    Пользователь заметил подозрительную активность и хочет "обнулить"
    все сессии одной кнопкой, как в Google "Sign out of all devices".
    """,
)
async def terminate_all_user_sessions_api(
    request: TerminateAllSessionsRequest,
    current_user: Annotated[
        "CurrentUserInfo", Depends(get_current_user_with_session)
    ],
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """
    Завершает все сессии пользователя, кроме текущей (опционально).

    - Завершает все или почти все сессии
    - Добавляет токены в blacklist
    - Логирует массовое завершение
    """

    user_id = current_user.id
    current_session_id = (
        current_user.session_id if request.keep_current else None
    )

    # Завершаем все сессии (кроме текущей, если указано)
    terminated_count = await terminate_all_user_sessions(
        db=db, user_id=user_id, keep_session_id=current_session_id
    )

    # Логируем массовое завершение
    await log_security_event(
        db=db,
        event_type="all_sessions_terminated",
        user_id=user_id,
        session_id=current_session_id,
        details={
            "reason": "user_requested",
            "keep_current": request.keep_current,
            "terminated_count": terminated_count,
        },
    )

    log.info(
        "user.sessions.all_terminated",
        user_id=str(user_id),
        terminated_count=terminated_count,
        keep_current=request.keep_current,
    )

    return TerminateAllSessionsResponse(
        message=(
            "All sessions terminated"
            if terminated_count > 0
            else "No sessions to terminate"
        ),
        success=True,
        sessions_terminated=terminated_count,
        current_session_kept=request.keep_current,
    )
