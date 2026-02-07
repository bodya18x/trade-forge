"""
Валидация стратегий.

Этот модуль содержит логику валидации AST-дерева стратегий,
названий стратегий и обработку ошибок валидации.
"""

from __future__ import annotations

import uuid
from typing import List, Set

from fastapi import Request
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_schemas import (
    StrategyDefinition,
    StrategyValidationRequest,
    StrategyValidationResponse,
    ValidationErrorDetail,
)

from app.crud.crud_strategies import check_strategy_name_exists

from .error_translator import ErrorTranslator
from .indicator_extractor import IndicatorExtractor
from .indicator_key_validator import IndicatorKeyValidator


class StrategyValidator:
    """
    Валидатор стратегий.

    Выполняет валидацию названий, AST-дерева стратегий и
    формирует единообразные ответы в RFC 7807 формате.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализирует валидатор стратегий.

        Args:
            db: Асинхронная сессия базы данных
        """
        self.db = db
        self.indicator_extractor = IndicatorExtractor()
        self.indicator_key_validator = IndicatorKeyValidator()
        self.error_translator = ErrorTranslator()

    async def validate_name(
        self,
        name: str,
        user_id: uuid.UUID,
        strategy_id: uuid.UUID | None = None,
    ) -> list[ValidationErrorDetail]:
        """
        Валидирует название стратегии.

        Args:
            name: Название стратегии
            user_id: UUID пользователя
            strategy_id: UUID стратегии (для исключения при редактировании)

        Returns:
            Список ошибок валидации (пустой если валидация прошла)
        """
        errors = []
        name = name.strip() if isinstance(name, str) else str(name)

        # Проверка минимальной длины
        if len(name) < 3:
            errors.append(
                ValidationErrorDetail(
                    loc=["name"],
                    msg="Название стратегии должно содержать минимум 3 символа",
                    type="min_length",
                )
            )
            return errors

        # Проверка максимальной длины
        if len(name) > 255:
            errors.append(
                ValidationErrorDetail(
                    loc=["name"],
                    msg="Название стратегии не может превышать 255 символов",
                    type="max_length",
                )
            )
            return errors

        # Проверка уникальности
        name_exists = await check_strategy_name_exists(
            self.db,
            user_id=user_id,
            name=name,
            exclude_strategy_id=strategy_id,
        )

        if name_exists:
            errors.append(
                ValidationErrorDetail(
                    loc=["name"],
                    msg=f"Стратегия с названием '{name}' уже существует",
                    type="unique_constraint",
                )
            )

        return errors

    def validate_entry_conditions(
        self, definition_dict: dict
    ) -> list[ValidationErrorDetail]:
        """
        Валидирует наличие условий входа в стратегии.

        Args:
            definition_dict: Словарь с определением стратегии

        Returns:
            Список ошибок валидации (пустой если валидация прошла)
        """
        errors = []

        # Проверяем наличие хотя бы одного условия входа
        entry_buy = definition_dict.get("entry_buy_conditions")
        entry_sell = definition_dict.get("entry_sell_conditions")

        # Проверяем все возможные "пустые" значения
        if (entry_buy is None or entry_buy == {} or entry_buy == []) and (
            entry_sell is None or entry_sell == {} or entry_sell == []
        ):
            errors.append(
                ValidationErrorDetail(
                    loc=["definition"],
                    msg="Стратегия должна содержать хотя бы одно условие входа в позицию (entry_buy_conditions или entry_sell_conditions)",
                    type="missing_entry_conditions",
                )
            )

        return errors

    def validate_exit_conditions(
        self, definition_dict: dict
    ) -> list[ValidationErrorDetail]:
        """
        Валидирует наличие условий выхода в стратегии.

        Args:
            definition_dict: Словарь с определением стратегии

        Returns:
            Список ошибок валидации (пустой если валидация прошла)
        """
        errors = []

        exit_conditions = definition_dict.get("exit_conditions")

        if (
            exit_conditions is None
            or exit_conditions == {}
            or exit_conditions == []
        ):
            errors.append(
                ValidationErrorDetail(
                    loc=["definition", "exit_conditions"],
                    msg="Стратегия должна содержать условия выхода из позиции",
                    type="missing_exit_conditions",
                )
            )

        return errors

    async def validate_definition(
        self,
        definition: StrategyDefinition,
        user_id: uuid.UUID | None = None,
        name: str | None = None,
        strategy_id: uuid.UUID | None = None,
    ) -> StrategyValidationResponse:
        """
        Валидирует определение стратегии.

        Args:
            definition: Pydantic модель определения стратегии
            user_id: UUID пользователя (опционально)
            name: Название стратегии (опционально)
            strategy_id: UUID стратегии для исключения при проверке уникальности

        Returns:
            Результат валидации в RFC 7807 формате
        """
        all_errors: List[ValidationErrorDetail] = []

        # 1. Валидация названия (если передано)
        if name is not None and user_id is not None:
            name_errors = await self.validate_name(name, user_id, strategy_id)
            all_errors.extend(name_errors)

        # 2. Валидация определения стратегии
        definition_dict = definition.model_dump()

        # Проверяем условия входа
        entry_errors = self.validate_entry_conditions(definition_dict)
        all_errors.extend(entry_errors)

        # 3. Извлекаем и валидируем ключи индикаторов
        indicator_keys = self.indicator_extractor.extract_indicator_keys(
            definition_dict
        )
        key_validation_errors = (
            self.indicator_key_validator.validate_indicator_keys(
                indicator_keys
            )
        )
        all_errors.extend(key_validation_errors)

        # 4. Извлекаем базовые ключи для required_indicators
        required_indicators = list(
            self.indicator_extractor.extract_base_keys(indicator_keys)
        )

        # 5. Формируем ответ
        if all_errors:
            return StrategyValidationResponse(
                is_valid=False,
                required_indicators=required_indicators,
                type="https://trade-forge.ru/errors/validation",
                title="Ошибка валидации",
                status=422,
                detail="Одно или несколько полей не прошли валидацию.",
                errors=all_errors,
            )

        return StrategyValidationResponse(
            is_valid=True,
            required_indicators=required_indicators,
        )

    async def validate_with_business_logic(
        self,
        user_id: uuid.UUID,
        definition: StrategyDefinition,
        name: str | None = None,
        strategy_id: uuid.UUID | None = None,
    ) -> StrategyValidationResponse:
        """
        Валидирует стратегию с бизнес-логикой (включая обязательность exit_conditions).

        Args:
            user_id: UUID пользователя
            definition: Определение стратегии
            name: Название стратегии (опционально)
            strategy_id: UUID стратегии для исключения при проверке уникальности

        Returns:
            Результат валидации в RFC 7807 формате
        """
        all_errors: List[ValidationErrorDetail] = []

        # 1. Валидация определения
        definition_dict = definition.model_dump()

        # Проверяем условия выхода (обязательны для бизнес-логики)
        exit_errors = self.validate_exit_conditions(definition_dict)
        all_errors.extend(exit_errors)

        # Проверяем условия входа
        entry_errors = self.validate_entry_conditions(definition_dict)
        all_errors.extend(entry_errors)

        # 2. Валидация названия (если передано)
        if name is not None:
            name_errors = await self.validate_name(name, user_id, strategy_id)
            all_errors.extend(name_errors)

        # 3. Извлекаем и валидируем ключи индикаторов
        indicator_keys = self.indicator_extractor.extract_indicator_keys(
            definition_dict
        )
        key_validation_errors = (
            self.indicator_key_validator.validate_indicator_keys(
                indicator_keys
            )
        )
        all_errors.extend(key_validation_errors)

        # 4. Извлекаем базовые ключи для required_indicators
        required_indicators = list(
            self.indicator_extractor.extract_base_keys(indicator_keys)
        )

        # 4. Формируем ответ
        if all_errors:
            return StrategyValidationResponse(
                is_valid=False,
                required_indicators=required_indicators,
                type="https://trade-forge.ru/errors/validation",
                title="Ошибка валидации",
                status=422,
                detail="Одно или несколько полей не прошли валидацию.",
                errors=all_errors,
            )

        return StrategyValidationResponse(
            is_valid=True,
            required_indicators=required_indicators,
        )

    def _normalize_error_location(self, loc: tuple) -> List[str]:
        """
        Нормализует пути ошибок для консистентности.

        Args:
            loc: Кортеж с путем к ошибке

        Returns:
            Нормализованный список строк пути
        """
        normalized = []
        for part in loc:
            part_str = str(part)
            # Пропускаем 'body' префикс для консистентности
            if part_str != "body":
                normalized.append(part_str)

        return normalized if normalized else ["body"]

    async def validate_raw_request(
        self, user_id: uuid.UUID, request: Request
    ) -> StrategyValidationResponse:
        """
        Валидирует сырой запрос стратегии (объединяет Pydantic и бизнес-логику).

        Args:
            user_id: UUID пользователя
            request: Raw FastAPI Request объект

        Returns:
            Результат валидации в RFC 7807 формате
        """
        try:
            # Получаем сырые данные
            try:
                raw_data = await request.json()
            except Exception:
                return StrategyValidationResponse(
                    is_valid=False,
                    required_indicators=[],
                    type="https://trade-forge.ru/errors/validation",
                    title="Ошибка валидации",
                    status=422,
                    detail="Одно или несколько полей не прошли валидацию.",
                    errors=[
                        ValidationErrorDetail(
                            loc=["body"],
                            msg="Неверный формат JSON",
                            type="json_invalid",
                        )
                    ],
                )

            # Собираем все ошибки
            all_errors: List[ValidationErrorDetail] = []
            definition = None
            name = None
            strategy_id = None

            # 1. Pydantic валидация с дедупликацией
            try:
                validated_request = StrategyValidationRequest(**raw_data)
                definition = validated_request.definition
                name = validated_request.name
                strategy_id = validated_request.strategy_id
            except PydanticValidationError as e:
                # Дедуплицируем и нормализуем Pydantic ошибки
                seen_errors: Set[tuple] = set()
                for error in e.errors():
                    normalized_loc = self._normalize_error_location(
                        error["loc"]
                    )
                    error_signature = (
                        tuple(normalized_loc),
                        error["type"],
                        error["msg"],
                    )

                    if error_signature not in seen_errors:
                        seen_errors.add(error_signature)
                        all_errors.append(
                            ValidationErrorDetail(
                                loc=normalized_loc,
                                msg=self.error_translator.translate(
                                    error["msg"], error["type"]
                                ),
                                type=error["type"],
                            )
                        )

                # Пытаемся извлечь данные из сырого запроса
                definition = raw_data.get("definition")
                name = raw_data.get("name")
                strategy_id_str = raw_data.get("strategy_id")
                try:
                    strategy_id = (
                        uuid.UUID(strategy_id_str) if strategy_id_str else None
                    )
                except (ValueError, TypeError):
                    strategy_id = None

            # 2. Бизнес-логика валидация определения
            if definition is not None and isinstance(definition, dict):
                entry_errors = self.validate_entry_conditions(definition)
                all_errors.extend(entry_errors)

            # 3. Валидация названия
            if name is not None:
                name_errors = await self.validate_name(
                    name, user_id, strategy_id
                )
                all_errors.extend(name_errors)

            # 4. Валидация ключей индикаторов
            if definition is not None and isinstance(definition, dict):
                indicator_keys = (
                    self.indicator_extractor.extract_indicator_keys(definition)
                )
                key_validation_errors = (
                    self.indicator_key_validator.validate_indicator_keys(
                        indicator_keys
                    )
                )
                all_errors.extend(key_validation_errors)

            # 5. Извлекаем индикаторы
            required_indicators = (
                self.indicator_extractor.safely_extract_indicators(definition)
            )

            # 5. Формируем финальный ответ
            if all_errors:
                return StrategyValidationResponse(
                    is_valid=False,
                    required_indicators=required_indicators,
                    type="https://trade-forge.ru/errors/validation",
                    title="Ошибка валидации",
                    status=422,
                    detail="Одно или несколько полей не прошли валидацию.",
                    errors=all_errors,
                )

            return StrategyValidationResponse(
                is_valid=True,
                required_indicators=required_indicators,
            )

        except Exception:
            # Логируем неожиданные ошибки
            return StrategyValidationResponse(
                is_valid=False,
                required_indicators=[],
                type="https://trade-forge.ru/errors/validation",
                title="Ошибка валидации",
                status=422,
                detail="Ошибка сервиса валидации.",
                errors=[
                    ValidationErrorDetail(
                        loc=["body"],
                        msg="Произошла внутренняя ошибка валидации",
                        type="internal_error",
                    )
                ],
            )
