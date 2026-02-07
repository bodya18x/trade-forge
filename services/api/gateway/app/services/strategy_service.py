"""
Сервис стратегий - Бизнес-логика для операций со стратегиями.
Валидирует, преобразует и обогащает запросы стратегий перед проксированием во внутренний API.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis
from tradeforge_logger import get_logger

from app.core.internal_api_utils import extract_internal_api_error_detail
from app.core.proxy_client import InternalAPIClient
from app.core.rate_limiting import check_user_rate_limits

log = get_logger(__name__)


class StrategyService:
    """
    Сервис бизнес-логики для операций со стратегиями.

    Этот сервис добавляет корректную валидацию, ограничение скорости и бизнес-логику
    поверх вызовов внутреннего API вместо слепого проксирования.
    """

    def __init__(self, redis: Redis, internal_client: InternalAPIClient):
        self.redis = redis
        self.internal_client = internal_client

    async def validate_strategy_definition(
        self,
        user_id: uuid.UUID,
        definition: Dict[str, Any],
        name: Optional[str] = None,
        strategy_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        Валидирует определение стратегии и название перед отправкой во внутренний API.

        Args:
            user_id: UUID пользователя
            definition: Определение стратегии от пользователя
            name: Название стратегии для проверки уникальности (опционально)
            strategy_id: ID редактируемой стратегии (исключается из проверки уникальности)

        Returns:
            Результат валидации из внутреннего API

        Raises:
            HTTPException: При ошибках валидации
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(self.redis, user_id, "POST")

            # Убираем базовую валидацию здесь - всё делаем во внутреннем API
            # чтобы объединить Pydantic ошибки и кастомные ошибки в одном месте

            # Отправляем во внутренний API для детальной валидации
            json_data = {"definition": definition}
            if name is not None:
                json_data["name"] = name
            if strategy_id is not None:
                json_data["strategy_id"] = str(strategy_id)

            response = await self.internal_client.post(
                path="/api/v1/strategies/validate",
                user_id=user_id,
                json_data=json_data,
            )

            if response.status_code != 200:
                # Безопасно извлекаем детали ошибки
                detail = extract_internal_api_error_detail(response.text)
                if not detail.strip():
                    detail = (
                        "Валидация стратегии не прошла. Проверьте ваши данные."
                    )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            result = response.json()

            log.info(
                "strategy.validation.completed",
                user_id=str(user_id),
                is_valid=result.get("is_valid", False),
            )

            return result

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "strategy.validation.failed",
                user_id=str(user_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сервиса валидации стратегии",
            )

    async def validate_strategy_raw_request(
        self, user_id: uuid.UUID, request: Request, instance_url: str
    ) -> Dict[str, Any]:
        """
        Архитектурно чистая прокси-валидация: просто передает raw request во Internal API.
        Все сложная логика валидации (Pydantic + бизнес-логика) выполняется во Internal API.

        Args:
            user_id: UUID пользователя
            request: Сырой FastAPI Request
            instance_url: URL для включения в ответ ошибки (не используется в новой архитектуре)

        Returns:
            Результат валидации от Internal API (с санитизацией для безопасности)
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(self.redis, user_id, "POST")

            # Получаем сырые данные для передачи во Internal API
            try:
                raw_data = await request.json()
            except Exception:
                # Даже JSON ошибки обрабатываем во Internal API для консистентности
                raw_data = {}

            # Прямо передаем во Internal API - он источник истины для валидации
            response = await self.internal_client.post(
                path="/api/v1/strategies/validate",
                user_id=user_id,
                json_data=raw_data,
            )

            if response.status_code in (200, 422):
                # Получаем результат валидации
                result = response.json()

                # Добавляем instance URL для RFC 7807 соответствия, если нужно
                if (
                    not result.get("is_valid", True)
                    and "instance" not in result
                ):
                    result["instance"] = instance_url

                log.info(
                    "strategy.validation.completed",
                    user_id=str(user_id),
                    is_valid=result.get("is_valid", False),
                )

                return result
            else:
                # Ошибки Internal API
                detail = extract_internal_api_error_detail(response.text)
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "strategy.validation.failed",
                user_id=str(user_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сервиса валидации стратегии",
            )

    async def create_strategy(
        self,
        user_id: uuid.UUID,
        name: str,
        description: Optional[str],
        definition: Dict[str, Any],
        subscription_tier: str = "free",
    ) -> Dict[str, Any]:
        """
        Создает новую стратегию с корректной валидацией и ограничением скорости.

        Args:
            user_id: UUID пользователя
            name: Название стратегии
            description: Описание стратегии (опционально)
            definition: Определение стратегии

        Returns:
            Данные созданной стратегии

        Raises:
            HTTPException: При ошибках создания
        """
        try:
            # Применяем ограничение скорости (включая лимиты на конкретные ресурсы)
            await check_user_rate_limits(
                redis=self.redis,
                user_id=user_id,
                method="POST",
                subscription_tier=subscription_tier,
                resource_type="strategy",
            )

            # Бизнес-валидация не выполняется в Gateway - вся валидация происходит в Internal API

            # Создаем стратегию через внутренний API
            json_data = {"name": name, "definition": definition}
            if description is not None:
                json_data["description"] = description

            response = await self.internal_client.post(
                path="/api/v1/strategies/",
                user_id=user_id,
                json_data=json_data,
            )

            if response.status_code != 201:
                if response.status_code == 422:
                    # Безопасно извлекаем сообщение об ошибке валидации
                    detail = extract_internal_api_error_detail(response.text)
                    if not detail.strip():
                        detail = "Создание стратегии не прошло валидацию"
                elif response.status_code >= 500:
                    # Скрываем внутренние серверные ошибки
                    detail = "Произошла внутренняя ошибка сервера. Пожалуйста, попробуйте позже."
                else:
                    # Для других ошибок также извлекаем безопасное сообщение об ошибке
                    detail = extract_internal_api_error_detail(response.text)
                    if not detail.strip():
                        detail = "Не удалось создать стратегию. Пожалуйста, проверьте введенные данные."

                raise HTTPException(
                    status_code=response.status_code, detail=detail
                )

            strategy_data = response.json()

            log.info(
                "strategy.created",
                user_id=str(user_id),
                strategy_id=strategy_data.get("id"),
                strategy_name=name,
            )

            return strategy_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "strategy.creation.failed",
                user_id=str(user_id),
                strategy_name=name,
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сервиса создания стратегии",
            )

    async def get_user_strategies(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_direction: str = "desc",
    ) -> Dict[str, Any]:
        """
        Получает стратегии пользователя с валидацией и ограничением скорости.

        Args:
            user_id: UUID пользователя
            limit: Количество стратегий для возврата
            offset: Смещение для пагинации
            sort_by: Поле для сортировки
            sort_direction: Направление сортировки

        Returns:
            Пагинированный список стратегий
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(self.redis, user_id, "GET")

            # Валидация пагинации происходит в Internal API

            # Получаем стратегии из внутреннего API
            response = await self.internal_client.get(
                path="/api/v1/strategies/",
                user_id=user_id,
                params={
                    "limit": limit,
                    "offset": offset,
                    "sort_by": sort_by,
                    "sort_direction": sort_direction,
                },
            )

            if response.status_code >= 500:
                # Скрываем внутренние серверные ошибки
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Произошла внутренняя ошибка сервера. Пожалуйста, попробуйте позже.",
                )
            elif response.status_code != 200:
                # Для других ошибок извлекаем безопасное сообщение об ошибке
                detail = extract_internal_api_error_detail(response.text)
                if not detail.strip():
                    detail = "Не удалось получить стратегии. Пожалуйста, проверьте запрос."
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            strategies_data = response.json()

            log.info(
                "strategies.list.retrieved",
                user_id=str(user_id),
                count=len(strategies_data.get("items", [])),
                total=strategies_data.get("total", 0),
            )

            return strategies_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "strategies.list.retrieval.failed",
                user_id=str(user_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сервиса получения стратегий",
            )

    async def get_strategy(
        self, user_id: uuid.UUID, strategy_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Получает конкретную стратегию с валидацией.

        Args:
            user_id: UUID пользователя
            strategy_id: UUID стратегии

        Returns:
            Данные стратегии
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(self.redis, user_id, "GET")

            # Получаем стратегию из внутреннего API
            response = await self.internal_client.get(
                path=f"/api/v1/strategies/{strategy_id}", user_id=user_id
            )

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Стратегия не найдена или доступ запрещен",
                )
            elif response.status_code >= 500:
                # Скрываем внутренние серверные ошибки
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Произошла внутренняя ошибка сервера. Пожалуйста, попробуйте позже.",
                )
            elif response.status_code != 200:
                # Для других ошибок извлекаем безопасное сообщение об ошибке
                detail = extract_internal_api_error_detail(response.text)
                if not detail.strip():
                    detail = "Не удалось получить стратегию. Пожалуйста, проверьте запрос."
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            strategy_data = response.json()

            log.info(
                "strategy.retrieved",
                user_id=str(user_id),
                strategy_id=str(strategy_id),
            )

            return strategy_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "strategy.retrieval.failed",
                user_id=str(user_id),
                strategy_id=str(strategy_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сервиса получения стратегий",
            )

    async def update_strategy(
        self,
        user_id: uuid.UUID,
        strategy_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        definition: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Обновляет стратегию с валидацией.

        Args:
            user_id: UUID пользователя
            strategy_id: UUID стратегии
            name: Новое название стратегии (опционально)
            description: Новое описание стратегии (опционально)
            definition: Новое определение стратегии (опционально)

        Returns:
            Данные обновленной стратегии
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(self.redis, user_id, "PUT")

            update_data = {}

            # Добавляем название если предоставлено (валидация происходит в Internal API)
            if name is not None:
                update_data["name"] = name

            # Добавляем описание если предоставлено
            if description is not None:
                update_data["description"] = description

            # Добавляем определение если предоставлено (валидация происходит в Internal API)
            if definition is not None:
                update_data["definition"] = definition

            # Internal API обработает валидацию пустых обновлений

            # Обновляем стратегию через внутренний API
            response = await self.internal_client.put(
                path=f"/api/v1/strategies/{strategy_id}",
                user_id=user_id,
                json_data=update_data,
            )

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Стратегия не найдена или доступ запрещен",
                )
            elif response.status_code == 422:
                # Безопасно извлекаем сообщение об ошибке валидации
                detail = extract_internal_api_error_detail(response.text)
                if not detail.strip():
                    detail = "Обновление стратегии не прошло валидацию"
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=detail,
                )
            elif response.status_code >= 500:
                # Скрываем внутренние серверные ошибки
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Произошла внутренняя ошибка сервера. Пожалуйста, попробуйте позже.",
                )
            elif response.status_code != 200:
                # Для других ошибок также извлекаем безопасное сообщение об ошибке
                detail = extract_internal_api_error_detail(response.text)
                if not detail.strip():
                    detail = "Не удалось обновить стратегию. Пожалуйста, проверьте введенные данные."
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            strategy_data = response.json()

            log.info(
                "strategy.updated",
                user_id=str(user_id),
                strategy_id=str(strategy_id),
            )

            return strategy_data

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "strategy.update.failed",
                user_id=str(user_id),
                strategy_id=str(strategy_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сервиса обновления стратегии",
            )

    async def delete_strategy(
        self, user_id: uuid.UUID, strategy_id: uuid.UUID
    ) -> None:
        """
        Удаляет стратегию с валидацией.

        Args:
            user_id: UUID пользователя
            strategy_id: UUID стратегии
        """
        try:
            # Применяем ограничение скорости
            await check_user_rate_limits(self.redis, user_id, "DELETE")

            # Удаляем стратегию через внутренний API
            response = await self.internal_client.delete(
                path=f"/api/v1/strategies/{strategy_id}", user_id=user_id
            )

            if response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Стратегия не найдена или доступ запрещен",
                )
            elif response.status_code >= 500:
                # Скрываем внутренние серверные ошибки
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Произошла внутренняя ошибка сервера. Пожалуйста, попробуйте позже.",
                )
            elif response.status_code != 204:
                # Для других ошибок извлекаем безопасное сообщение об ошибке
                detail = extract_internal_api_error_detail(response.text)
                if not detail.strip():
                    detail = "Не удалось удалить стратегию. Пожалуйста, проверьте запрос."
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )

            log.info(
                "strategy.deleted",
                user_id=str(user_id),
                strategy_id=str(strategy_id),
            )

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                "strategy.deletion.failed",
                user_id=str(user_id),
                strategy_id=str(strategy_id),
                error=str(e),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сервиса удаления стратегии",
            )
