"""
Сервис для работы со стратегиями.

Координирует валидацию стратегий и обеспечение существования индикаторов.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_schemas import StrategyDefinition, StrategyValidationResponse

from app.crud.crud_indicators import (
    ensure_multiple_user_indicators_exist,
    parse_indicator_from_key,
)
from app.types import StrategyID, UserID

from .indicator_extractor import IndicatorExtractor
from .validation import StrategyValidator


class StrategyService:
    """
    Сервис для работы со стратегиями.

    Обеспечивает валидацию стратегий и управление связанными индикаторами.
    """

    def __init__(self, db_session: AsyncSession):
        """
        Инициализирует сервис стратегий.

        Args:
            db_session: Асинхронная сессия базы данных
        """
        self.db = db_session
        self.validator = StrategyValidator(db_session)
        self.indicator_extractor = IndicatorExtractor()

    async def validate_strategy_definition(
        self,
        definition: StrategyDefinition,
        user_id: UserID | None = None,
        name: str | None = None,
        strategy_id: StrategyID | None = None,
    ) -> StrategyValidationResponse:
        """
        Валидирует AST-дерево стратегии и название (если передано).

        Args:
            definition: Определение стратегии
            user_id: UUID пользователя (для проверки уникальности названия)
            name: Название стратегии (опционально)
            strategy_id: UUID стратегии (для исключения при редактировании)

        Returns:
            Результат валидации в RFC 7807 формате
        """
        return await self.validator.validate_definition(
            definition=definition,
            user_id=user_id,
            name=name,
            strategy_id=strategy_id,
        )

    async def ensure_strategy_indicators_exist(
        self, definition: StrategyDefinition
    ) -> None:
        """
        Обеспечивает существование всех индикаторов, используемых в стратегии.

        Массово создает записи в таблице users_indicators для всех
        индикаторов, используемых в стратегии.

        Args:
            definition: Определение стратегии
        """
        # Собираем все полные ключи индикаторов
        required_keys = self.indicator_extractor.extract_indicator_keys(
            definition.model_dump()
        )

        # Получаем базовые ключи индикаторов (без суффиксов) и дедуплицируем
        base_indicators = {}
        for key in required_keys:
            parsed = parse_indicator_from_key(key)

            # Создаем базовый ключ
            base_key = f"{parsed['name']}"
            if parsed["params"]:
                param_parts = []
                for param_name, param_value in parsed["params"].items():
                    param_parts.extend([param_name, str(param_value)])
                if param_parts:
                    base_key += "_" + "_".join(param_parts)

            # Дедуплицируем - один базовый индикатор независимо от количества суффиксов
            base_indicators[base_key] = {
                "indicator_key": base_key,
                "name": parsed["name"],
                "params": parsed["params"],
                "is_hot": False,  # По умолчанию не горячий
            }

        # Массово обеспечиваем существование базовых индикаторов
        indicators_to_ensure = list(base_indicators.values())
        await ensure_multiple_user_indicators_exist(
            self.db, indicators_to_ensure
        )

    async def validate_strategy_raw_request(
        self, user_id: UserID, request: Request
    ) -> StrategyValidationResponse:
        """
        Валидирует сырой запрос стратегии (Single Source of Truth для валидации).

        Объединяет Pydantic валидацию и бизнес-логику в едином месте.

        Args:
            user_id: UUID пользователя
            request: Raw FastAPI Request объект

        Returns:
            Результат валидации в RFC 7807 формате
        """
        return await self.validator.validate_raw_request(user_id, request)

    async def validate_strategy_with_business_logic(
        self,
        user_id: UserID,
        definition: StrategyDefinition,
        name: str | None = None,
        strategy_id: StrategyID | None = None,
    ) -> StrategyValidationResponse:
        """
        Валидирует стратегию с применением бизнес-логики.

        Используется когда базовая Pydantic валидация уже прошла успешно.

        Args:
            user_id: UUID пользователя
            definition: Валидированное определение стратегии
            name: Название стратегии (опционально)
            strategy_id: UUID стратегии (для исключения при проверке уникальности)

        Returns:
            Результат валидации в RFC 7807 формате
        """
        return await self.validator.validate_with_business_logic(
            user_id=user_id,
            definition=definition,
            name=name,
            strategy_id=strategy_id,
        )
