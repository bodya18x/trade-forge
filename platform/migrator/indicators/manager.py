"""
Утилита управления индикаторами Trade Forge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from tradeforge_logger import get_logger

from .schemas import (
    IndicatorKeyGenerator,
    IndicatorValidator,
    SystemIndicatorDefinition,
    SystemIndicatorsList,
)

logger = get_logger(__name__)


class IndicatorsManager:
    """Менеджер для управления системными индикаторами."""

    def __init__(self, database_url: str):
        """
        Инициализация менеджера.

        Args:
            database_url: URL подключения к PostgreSQL
        """
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.key_generator = IndicatorKeyGenerator()
        self.validator = IndicatorValidator()

    def load_indicators_from_json(
        self, file_path: Path
    ) -> SystemIndicatorsList:
        """
        Загружает индикаторы из JSON-файла.

        Args:
            file_path: Путь к JSON-файлу с индикаторами

        Returns:
            Валидированный список индикаторов

        Raises:
            IndicatorValidationError: При ошибках валидации
            FileNotFoundError: Если файл не найден
            json.JSONDecodeError: При ошибках парсинга JSON
        """
        if not file_path.exists():
            raise FileNotFoundError(
                f"Файл с индикаторами не найден: {file_path}"
            )

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self.validator.validate_indicators_list(data)

    def validate_json_schema(self, file_path: Path) -> bool:
        """
        Валидирует JSON-файл с индикаторами против схемы.

        Args:
            file_path: Путь к JSON-файлу

        Returns:
            True если валидация прошла успешно

        Raises:
            IndicatorValidationError: При ошибках валидации
        """
        try:
            self.load_indicators_from_json(file_path)
            logger.info(f"Валидация файла {file_path} прошла успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка валидации файла {file_path}: {e}")
            raise

    def sync_to_database(self, indicators_list: SystemIndicatorsList) -> None:
        """
        Синхронизирует индикаторы из списка с базой данных.

        Args:
            indicators_list: Список индикаторов для синхронизации

        Raises:
            SQLAlchemyError: При ошибках работы с БД
        """
        with self.SessionLocal() as session:
            try:
                # Очищаем существующие записи
                session.execute(
                    text("DELETE FROM trader_core.system_indicators")
                )

                # Вставляем новые записи
                for indicator in indicators_list.indicators:
                    self._insert_indicator(session, indicator)

                session.commit()
                logger.info(
                    f"Синхронизировано {len(indicators_list.indicators)} индикаторов"
                )

            except Exception as e:
                session.rollback()
                logger.error(f"Ошибка синхронизации с БД: {e}")
                raise

    def _insert_indicator(
        self, session: Session, indicator: SystemIndicatorDefinition
    ) -> None:
        """
        Вставляет один индикатор в БД.

        Args:
            session: Сессия SQLAlchemy
            indicator: Индикатор для вставки
        """
        query = text(
            """
            INSERT INTO trader_core.system_indicators (
                name, display_name, description, category, complexity,
                parameters_schema, output_schema, key_template, is_enabled
            ) VALUES (
                :name, :display_name, :description, :category, :complexity,
                :parameters_schema, :output_schema, :key_template, :is_enabled
            )
        """
        )

        frontend_config = (
            indicator.frontend_config.model_dump()
            if indicator.frontend_config
            else None
        )

        # Добавляем frontend_config в parameters_schema для удобства
        parameters_schema = indicator.parameters_schema.model_dump()
        if frontend_config:
            parameters_schema["frontend_config"] = frontend_config

        session.execute(
            query,
            {
                "name": indicator.name,
                "display_name": indicator.display_name,
                "description": indicator.description,
                "category": indicator.category.value,
                "complexity": indicator.complexity.value,
                "parameters_schema": json.dumps(parameters_schema),
                "output_schema": json.dumps(
                    indicator.output_schema.model_dump()
                ),
                "key_template": indicator.key_template,
                "is_enabled": indicator.is_enabled,
            },
        )

    def generate_example_keys(
        self, indicator_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Генерирует примеры ключей для заданного индикатора.

        Args:
            indicator_name: Имя индикатора

        Returns:
            Словарь с примерами ключей и параметров
        """
        with self.SessionLocal() as session:
            query = text(
                """
                SELECT name, parameters_schema, output_schema, key_template
                FROM trader_core.system_indicators
                WHERE name = :name AND is_enabled = true
            """
            )

            result = session.execute(
                query, {"name": indicator_name}
            ).fetchone()
            if not result:
                logger.warning(f"Индикатор {indicator_name} не найден")
                return None

            name, params_schema, output_schema, key_template = result

            # Генерируем примеры параметров на основе defaults
            example_params = {}
            for param_name, param_def in params_schema.get(
                "properties", {}
            ).items():
                if "default" in param_def:
                    example_params[param_name] = param_def["default"]
                elif param_def["type"] == "integer":
                    example_params[param_name] = param_def.get("minimum", 1)
                elif param_def["type"] == "number":
                    example_params[param_name] = param_def.get("minimum", 1.0)
                elif param_def["type"] == "boolean":
                    example_params[param_name] = True
                else:
                    example_params[param_name] = "example"

            # Генерируем ключи для всех выходных значений
            output_keys = list(output_schema.get("properties", {}).keys())

            if "{output_key}" in key_template:
                generated_keys = self.key_generator.generate_keys_for_outputs(
                    key_template, name, example_params, output_keys
                )
            else:
                generated_keys = [
                    self.key_generator.generate_key(
                        key_template, name, example_params
                    )
                ]

            return {
                "indicator_name": name,
                "example_parameters": example_params,
                "output_keys": output_keys,
                "generated_keys": generated_keys,
                "key_template": key_template,
            }

    def get_indicators_for_frontend(self) -> List[Dict[str, Any]]:
        """
        Получает список индикаторов для фронтенда.

        Returns:
            Список индикаторов с метаданными для UI
        """
        with self.SessionLocal() as session:
            query = text(
                """
                SELECT name, display_name, description, category, complexity,
                       parameters_schema, output_schema, key_template, is_enabled
                FROM trader_core.system_indicators
                WHERE is_enabled = true
                ORDER BY complexity, category, display_name
            """
            )

            results = session.execute(query).fetchall()
            indicators = []

            for row in results:
                (
                    name,
                    display_name,
                    description,
                    category,
                    complexity,
                    params_schema,
                    output_schema,
                    key_template,
                    is_enabled,
                ) = row

                # Извлекаем frontend_config если есть
                frontend_config = params_schema.pop("frontend_config", {})

                indicator_data = {
                    "name": name,
                    "display_name": display_name,
                    "description": description,
                    "category": category,
                    "complexity": complexity,
                    "parameters": params_schema.get("properties", {}),
                    "required_parameters": params_schema.get("required", []),
                    "outputs": output_schema.get("properties", {}),
                    "key_template": key_template,
                    "frontend_config": frontend_config,
                }

                indicators.append(indicator_data)

            return indicators

    def health_check(self) -> bool:
        """
        Проверяет работоспособность соединения с БД.

        Returns:
            True если соединение работает
        """
        try:
            with self.SessionLocal() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Ошибка подключения к БД: {e}")
            return False


class IndicatorsCLI:
    """CLI-интерфейс для управления индикаторами."""

    def __init__(self, manager: IndicatorsManager):
        """
        Инициализация CLI.

        Args:
            manager: Менеджер индикаторов
        """
        self.manager = manager

    def validate_command(self, json_file_path: str) -> None:
        """
        Команда валидации JSON-файла.

        Args:
            json_file_path: Путь к JSON-файлу
        """
        try:
            path = Path(json_file_path)
            self.manager.validate_json_schema(path)
            print(f"✅ Файл {json_file_path} прошел валидацию успешно")
        except Exception as e:
            print(f"❌ Ошибка валидации: {e}")
            raise

    def sync_command(self, json_file_path: str) -> None:
        """
        Команда синхронизации с БД.

        Args:
            json_file_path: Путь к JSON-файлу
        """
        try:
            path = Path(json_file_path)
            indicators_list = self.manager.load_indicators_from_json(path)
            self.manager.sync_to_database(indicators_list)
            print(
                f"✅ Синхронизировано {len(indicators_list.indicators)} индикаторов"
            )
        except Exception as e:
            print(f"❌ Ошибка синхронизации: {e}")
            raise

    def generate_keys_command(self, indicator_name: str) -> None:
        """
        Команда генерации примеров ключей.

        Args:
            indicator_name: Имя индикатора
        """
        result = self.manager.generate_example_keys(indicator_name)
        if result:
            print(f"🔑 Примеры ключей для индикатора '{indicator_name}':")
            print(f"Шаблон: {result['key_template']}")
            print(
                f"Примеры параметров: {json.dumps(result['example_parameters'], indent=2, ensure_ascii=False)}"
            )
            print(f"Сгенерированные ключи:")
            for key in result["generated_keys"]:
                print(f"  - {key}")
        else:
            print(f"❌ Индикатор '{indicator_name}' не найден")

    def list_command(self) -> None:
        """Команда получения списка индикаторов."""
        indicators = self.manager.get_indicators_for_frontend()
        print(f"📊 Доступные индикаторы ({len(indicators)}):")

        for indicator in indicators:
            print(f"\n🔹 {indicator['display_name']} ({indicator['name']})")
            print(f"   Категория: {indicator['category']}")
            print(f"   Сложность: {indicator['complexity']}")
            print(f"   Параметры: {len(indicator['parameters'])}")
            print(f"   Выходы: {list(indicator['outputs'].keys())}")

    def health_command(self) -> None:
        """Команда проверки здоровья системы."""
        if self.manager.health_check():
            print("✅ Соединение с БД работает")
        else:
            print("❌ Ошибка соединения с БД")
            raise ConnectionError("Не удается подключиться к базе данных")
