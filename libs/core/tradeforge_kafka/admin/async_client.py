"""
Асинхронная обертка над KafkaAdmin для использования в async окружении.
"""

from __future__ import annotations

import asyncio

from confluent_kafka.admin import TopicMetadata

from .client import KafkaAdmin


class AsyncKafkaAdmin:
    """
    Асинхронная обёртка над KafkaAdmin.

    Запускает все операции KafkaAdmin в thread pool,
    предоставляя полностью асинхронный API.

    Example:
        ```python
        async def main():
            admin = AsyncKafkaAdmin(bootstrap_servers="localhost:9092")

            # Проверка здоровья
            health = await admin.healthcheck()
            print(f"Kafka status: {health['status']}")

            # Создание топика
            await admin.create_topic(
                topic_name="my-topic",
                num_partitions=3,
                replication_factor=1
            )

            # Сравнение конфигурации
            diff = await admin.compare_topic_config(
                "my-topic",
                {"retention.ms": "86400000"}
            )

        asyncio.run(main())
        ```
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        admin_client_config: dict | None = None,
    ):
        """
        Инициализация асинхронного admin клиента.

        Args:
            bootstrap_servers: Адрес Kafka брокеров
            admin_client_config: Дополнительная конфигурация AdminClient
        """
        self._admin = KafkaAdmin(
            bootstrap_servers=bootstrap_servers,
            admin_client_config=admin_client_config,
        )

    async def create_topic(
        self,
        topic_name: str,
        num_partitions: int = 1,
        replication_factor: int = 1,
        config: dict | None = None,
        timeout: float = 10.0,
        validate_only: bool = False,
    ) -> None:
        """
        Асинхронное создание топика.

        Args:
            topic_name: Название топика
            num_partitions: Количество партиций
            replication_factor: Фактор репликации
            config: Дополнительная конфигурация
            timeout: Таймаут операции
            validate_only: Только валидация без создания
        """
        await asyncio.to_thread(
            self._admin.create_topic,
            topic_name,
            num_partitions,
            replication_factor,
            config,
            timeout,
            validate_only,
        )

    async def topic_exists(
        self, topic_name: str, timeout: float = 10.0
    ) -> bool:
        """
        Асинхронная проверка существования топика.

        Args:
            topic_name: Название топика
            timeout: Таймаут операции

        Returns:
            True если топик существует
        """
        return await asyncio.to_thread(
            self._admin.topic_exists, topic_name, timeout
        )

    async def list_topics(self, timeout: float = 10.0) -> list[str]:
        """
        Асинхронное получение списка топиков.

        Args:
            timeout: Таймаут операции

        Returns:
            Список названий топиков
        """
        return await asyncio.to_thread(self._admin.list_topics, timeout)

    async def delete_topic(
        self, topic_name: str, timeout: float = 10.0
    ) -> None:
        """
        Асинхронное удаление топика.

        Args:
            topic_name: Название топика
            timeout: Таймаут операции
        """
        await asyncio.to_thread(self._admin.delete_topic, topic_name, timeout)

    async def add_partitions(
        self, topic_name: str, total_count: int, timeout: float = 10.0
    ) -> None:
        """
        Асинхронное увеличение количества партиций.

        Args:
            topic_name: Название топика
            total_count: Итоговое количество партиций
            timeout: Таймаут операции
        """
        await asyncio.to_thread(
            self._admin.add_partitions, topic_name, total_count, timeout
        )

    async def describe_configs(
        self, topic_name: str, timeout: float = 10.0
    ) -> dict:
        """
        Асинхронное получение конфигурации топика.

        Args:
            topic_name: Название топика
            timeout: Таймаут операции

        Returns:
            Словарь с конфигурацией
        """
        return await asyncio.to_thread(
            self._admin.describe_configs, topic_name, timeout
        )

    async def alter_configs(
        self, topic_name: str, new_config: dict, timeout: float = 10.0
    ) -> None:
        """
        Асинхронное изменение конфигурации топика.

        Args:
            topic_name: Название топика
            new_config: Новая конфигурация
            timeout: Таймаут операции
        """
        await asyncio.to_thread(
            self._admin.alter_configs, topic_name, new_config, timeout
        )

    async def compare_topic_config(
        self, topic_name: str, expected_config: dict, timeout: float = 10.0
    ) -> dict[str, tuple[str | None, str]]:
        """
        Асинхронное сравнение конфигурации топика с ожидаемой.

        Args:
            topic_name: Название топика
            expected_config: Ожидаемая конфигурация
            timeout: Таймаут операции

        Returns:
            Словарь с расхождениями
        """
        return await asyncio.to_thread(
            self._admin.compare_topic_config,
            topic_name,
            expected_config,
            timeout,
        )

    async def get_topic_metadata(
        self, topic_name: str, timeout: float = 10.0
    ) -> TopicMetadata:
        """
        Асинхронное получение метаданных топика (партиции, реплики и т.д.)..

        Args:
            topic_name: Название топика.
            timeout: Таймаут операции в секундах.

        Returns:
            TopicMetadata объект с информацией о топике.
        """
        return await asyncio.to_thread(
            self._admin.get_topic_metadata, topic_name, timeout
        )

    async def healthcheck(self, timeout: float = 5.0) -> dict:
        """
        Асинхронная проверка здоровья Kafka кластера.

        Args:
            timeout: Таймаут операции

        Returns:
            Словарь со статусом кластера
        """
        return await asyncio.to_thread(self._admin.healthcheck, timeout)
