"""
Kafka мигратор с поддержкой создания и обновления топиков.

Поддерживает:
- Создание новых топиков
- Обновление конфигурации существующих топиков
- Изменение количества партиций (только увеличение)
- Валидацию конфигурации из YAML
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError
from tradeforge_kafka.admin.client import KafkaAdmin

from config.settings import MigratorSettings

from .base import BaseMigrator, MigrationResult, MigrationStatus


class TopicConfigModel(BaseModel):
    """
    Pydantic модель для конфигурации топика.

    Attributes:
        name: Название топика
        partitions: Количество партиций
        replication: Фактор репликации
        config: Дополнительная конфигурация топика
    """

    name: str = Field(..., min_length=1, description="Название топика")
    partitions: int = Field(1, ge=1, description="Количество партиций")
    replication: int = Field(1, ge=1, description="Фактор репликации")
    config: Dict[str, str] = Field(
        default_factory=dict, description="Конфигурация топика"
    )


class KafkaTopicsConfig(BaseModel):
    """
    Pydantic модель для всей конфигурации топиков.

    Attributes:
        topics: Список топиков
    """

    topics: List[TopicConfigModel] = Field(
        default_factory=list, description="Список топиков"
    )


@dataclass
class TopicUpdateResult:
    """
    Результат обновления топика.

    Attributes:
        topic_name: Название топика
        action: Действие (created/updated/skipped)
        changes: Описание изменений
    """

    topic_name: str
    action: str  # created, updated, skipped
    changes: Optional[Dict[str, Any]] = None


class KafkaMigrator(BaseMigrator):
    """
    Мигратор для Kafka топиков.

    Создает новые топики и обновляет конфигурацию существующих
    на основе декларативного YAML-файла.
    """

    def __init__(self, settings: MigratorSettings):
        """
        Инициализация Kafka мигратора.

        Args:
            settings: Настройки миграций
        """
        super().__init__(settings, "kafka_migrator")
        self.config_path = Path("kafka_topics.yml")
        self._admin: Optional[KafkaAdmin] = None

    @property
    def admin(self) -> KafkaAdmin:
        """
        Получить Kafka Admin клиент.

        Returns:
            Kafka Admin клиент
        """
        if self._admin is None:
            self._admin = KafkaAdmin(
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS
            )
        return self._admin

    async def health_check(self) -> bool:
        """
        Проверка доступности Kafka.

        Returns:
            True если Kafka доступен
        """
        self.logger.debug(
            "kafka_migrator.health_check_started",
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
        )

        max_retries = 10
        retry_delay = 3

        for attempt in range(1, max_retries + 1):
            try:
                # Пытаемся получить список топиков
                topics = set(self.admin.list_topics(timeout=5.0))
                self.logger.debug(
                    "kafka_migrator.existing_topics_found",
                    count=len(topics),
                )
                self._log_health_check_success()
                return True

            except Exception as e:
                self.logger.warning(
                    "kafka_migrator.health_check_attempt_failed",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(e),
                )

                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    self._log_health_check_failed(e)
                    return False

        return False

    async def run(self) -> MigrationResult:
        """
        Выполнение провижининга Kafka топиков.

        Returns:
            Результат выполнения
        """
        try:
            # Загружаем и валидируем конфигурацию
            config = await self._load_and_validate_config()

            # Получаем список существующих топиков
            existing_topics = set(self.admin.list_topics(timeout=10.0))
            self.logger.info(
                "kafka_migrator.existing_topics",
                count=len(existing_topics),
            )

            # Обрабатываем каждый топик из конфигурации
            results: List[TopicUpdateResult] = []

            for topic_def in config.topics:
                result = await self._process_topic(topic_def, existing_topics)
                results.append(result)

            # Подсчитываем статистику
            created = sum(1 for r in results if r.action == "created")
            updated = sum(1 for r in results if r.action == "updated")
            skipped = sum(1 for r in results if r.action == "skipped")

            self.logger.info(
                "kafka_migrator.provisioning_summary",
                total_topics=len(results),
                created=created,
                updated=updated,
                skipped=skipped,
            )

            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.SUCCESS,
                duration_seconds=0.0,
                migrations_applied=created + updated,
                details={
                    "created": created,
                    "updated": updated,
                    "skipped": skipped,
                    "results": [
                        {
                            "topic": r.topic_name,
                            "action": r.action,
                            "changes": r.changes,
                        }
                        for r in results
                    ],
                },
            )

        except Exception as e:
            self.logger.error(
                "kafka_migrator.provisioning_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return MigrationResult(
                migrator_name=self.component_name,
                status=MigrationStatus.FAILED,
                duration_seconds=0.0,
                error=str(e),
            )

    async def get_migration_status(self) -> Dict[str, Any]:
        """
        Получение статуса Kafka топиков.

        Returns:
            Словарь со статусом топиков
        """
        try:
            config = await self._load_and_validate_config()
            existing_topics = set(self.admin.list_topics(timeout=10.0))

            defined_topics = {t.name for t in config.topics}
            missing_topics = defined_topics - existing_topics
            extra_topics = existing_topics - defined_topics

            return {
                "bootstrap_servers": self.settings.KAFKA_BOOTSTRAP_SERVERS,
                "defined_topics": list(defined_topics),
                "existing_topics": list(existing_topics),
                "missing_topics": list(missing_topics),
                "extra_topics": list(extra_topics),
                "is_up_to_date": len(missing_topics) == 0,
            }
        except Exception as e:
            return {
                "bootstrap_servers": self.settings.KAFKA_BOOTSTRAP_SERVERS,
                "error": str(e),
                "is_up_to_date": False,
            }

    async def _load_and_validate_config(self) -> KafkaTopicsConfig:
        """
        Загрузить и валидировать конфигурацию топиков из YAML.

        Returns:
            Валидированная конфигурация

        Raises:
            FileNotFoundError: Если файл не найден
            ValidationError: Если конфигурация невалидна
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}"
            )

        self.logger.debug(
            "kafka_migrator.loading_config",
            path=str(self.config_path),
        )

        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        try:
            config = KafkaTopicsConfig(**raw_config)
            self.logger.info(
                "kafka_migrator.config_validated",
                topics_count=len(config.topics),
            )
            return config

        except ValidationError as e:
            self.logger.error(
                "kafka_migrator.config_validation_failed",
                errors=e.errors(),
            )
            raise

    async def _process_topic(
        self, topic_def: TopicConfigModel, existing_topics: set[str]
    ) -> TopicUpdateResult:
        """
        Обработать один топик (создать или обновить).

        Args:
            topic_def: Определение топика из конфигурации
            existing_topics: Множество существующих топиков

        Returns:
            Результат обработки топика
        """
        if topic_def.name not in existing_topics:
            # Создаем новый топик
            return await self._create_topic(topic_def)
        else:
            # Обновляем существующий топик
            return await self._update_topic(topic_def)

    async def _create_topic(
        self, topic_def: TopicConfigModel
    ) -> TopicUpdateResult:
        """
        Создать новый топик.

        Args:
            topic_def: Определение топика

        Returns:
            Результат создания
        """
        self.logger.info(
            "kafka_migrator.creating_topic",
            topic=topic_def.name,
            partitions=topic_def.partitions,
            replication=topic_def.replication,
        )

        try:
            self.admin.create_topic(
                topic_name=topic_def.name,
                num_partitions=topic_def.partitions,
                replication_factor=topic_def.replication,
                config=topic_def.config,
            )

            self.logger.info(
                "kafka_migrator.topic_created",
                topic=topic_def.name,
            )

            return TopicUpdateResult(
                topic_name=topic_def.name,
                action="created",
                changes={
                    "partitions": topic_def.partitions,
                    "replication": topic_def.replication,
                    "config": topic_def.config,
                },
            )

        except Exception as e:
            # Проверяем, не был ли топик создан параллельно
            if "already exists" in str(e).lower():
                self.logger.warning(
                    "kafka_migrator.topic_already_exists",
                    topic=topic_def.name,
                )
                return TopicUpdateResult(
                    topic_name=topic_def.name,
                    action="skipped",
                    changes={"reason": "Topic created concurrently"},
                )
            else:
                raise

    async def _update_topic(
        self, topic_def: TopicConfigModel
    ) -> TopicUpdateResult:
        """
        Обновить существующий топик.

        Может обновить:
        - Количество партиций (только увеличение)
        - Конфигурацию топика

        Args:
            topic_def: Определение топика

        Returns:
            Результат обновления
        """
        self.logger.debug(
            "kafka_migrator.checking_topic_for_updates",
            topic=topic_def.name,
        )

        changes = {}

        # Получаем текущее состояние топика через KafkaAdmin
        topic_metadata = self.admin.get_topic_metadata(topic_def.name)

        # Проверяем партиции
        current_partitions = len(topic_metadata.partitions)
        if topic_def.partitions > current_partitions:
            self.logger.info(
                "kafka_migrator.increasing_partitions",
                topic=topic_def.name,
                from_partitions=current_partitions,
                to_partitions=topic_def.partitions,
            )

            # Правильный метод из tradeforge_kafka: add_partitions
            self.admin.add_partitions(topic_def.name, topic_def.partitions)
            changes["partitions"] = {
                "from": current_partitions,
                "to": topic_def.partitions,
            }

        elif topic_def.partitions < current_partitions:
            self.logger.warning(
                "kafka_migrator.cannot_decrease_partitions",
                topic=topic_def.name,
                current_partitions=current_partitions,
                desired_partitions=topic_def.partitions,
            )

        # Обновляем конфигурацию
        if topic_def.config:
            self.logger.info(
                "kafka_migrator.updating_topic_config",
                topic=topic_def.name,
                config_keys=list(topic_def.config.keys()),
            )

            # Правильный метод из tradeforge_kafka: alter_configs
            self.admin.alter_configs(topic_def.name, topic_def.config)
            changes["config"] = topic_def.config

        if changes:
            self.logger.info(
                "kafka_migrator.topic_updated",
                topic=topic_def.name,
                changes=changes,
            )
            return TopicUpdateResult(
                topic_name=topic_def.name,
                action="updated",
                changes=changes,
            )
        else:
            self.logger.debug(
                "kafka_migrator.topic_up_to_date",
                topic=topic_def.name,
            )
            return TopicUpdateResult(
                topic_name=topic_def.name,
                action="skipped",
                changes={"reason": "No changes needed"},
            )
