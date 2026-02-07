"""
Административный клиент для управления Kafka топиками.

Обёртка над AdminClient из confluent_kafka с расширенными возможностями.
"""

from __future__ import annotations

import time

from confluent_kafka.admin import (
    AdminClient,
    ConfigResource,
    NewPartitions,
    NewTopic,
    TopicMetadata,
)
from confluent_kafka.cimpl import KafkaException
from tradeforge_logger import get_logger


class KafkaAdmin:
    """
    Класс-обёртка над AdminClient из confluent_kafka.
    Упрощает операции по созданию, модификации и удалению топиков, а также
    работу с конфигурациями топиков.

    Пример использования:
    -------------------
    from tradeforge_kafka.admin.client import KafkaAdmin

    admin = KafkaAdmin(bootstrap_servers='localhost:9092')

    # Проверка здоровья
    health = admin.healthcheck()
    if health['status'] == 'healthy':
        print(f"Kafka OK: {health['broker_count']} brokers")

    # Создание топика
    admin.create_topic(
        topic_name='test_topic',
        num_partitions=3,
        replication_factor=1,
        config={'cleanup.policy': 'delete', 'retention.ms': '60000'}
    )

    # Сравнение конфигурации
    diff = admin.compare_topic_config(
        'test_topic',
        {'retention.ms': '86400000'}
    )
    if diff:
        print(f"Config drift: {diff}")

    # Удаление топика
    admin.delete_topic('test_topic')
    """

    logger = get_logger(__name__)

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        admin_client_config: dict = None,
    ):
        """
        Инициализация административного клиента Kafka.

        Args:
            bootstrap_servers: Адрес(а) Kafka-брокеров.
            admin_client_config: Дополнительные параметры для AdminClient.
                Например, {"security.protocol": "SASL_PLAINTEXT", "sasl.mechanism": "PLAIN"}
        """
        config = admin_client_config or {}
        config["bootstrap.servers"] = bootstrap_servers
        self.admin_client = AdminClient(config)

    def create_topic(
        self,
        topic_name: str,
        num_partitions: int = 1,
        replication_factor: int = 1,
        config: dict = None,
        timeout: float = 10.0,
        validate_only: bool = False,
    ):
        """
        Создаёт топик с указанными параметрами.

        Args:
            topic_name: Название топика.
            num_partitions: Количество партиций.
            replication_factor: Фактор репликации.
            config: Дополнительная конфигурация (dict).
            timeout: Таймаут операции в секундах.
            validate_only: При True не создаёт топик, а только валидирует возможность создания.

        Raises:
            RuntimeError: Если топик уже существует или возникла ошибка создания.
        """
        new_topic = NewTopic(
            topic=topic_name,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
            config=config,
        )
        futures = self.admin_client.create_topics(
            [new_topic], request_timeout=timeout, validate_only=validate_only
        )

        # Обработка результата
        for topic, future in futures.items():
            try:
                future.result(timeout=timeout)
                self.logger.info(f"Топик '{topic}' успешно создан.")
            except KafkaException as e:
                raise RuntimeError(
                    f"Ошибка при создании топика '{topic}': {e}"
                )

    def topic_exists(self, topic_name: str, timeout: float = 10.0) -> bool:
        """
        Проверяет существование топика.

        Args:
            topic_name: Название топика.
            timeout: Таймаут в секундах.

        Returns:
            True если топик существует, иначе False.
        """
        metadata = self.admin_client.list_topics(timeout=timeout)
        return topic_name in metadata.topics

    def list_topics(self, timeout: float = 10.0) -> list:
        """
        Возвращает список названий всех топиков в кластере.

        Args:
            timeout: Таймаут в секундах.

        Returns:
            Список названий топиков.
        """
        metadata = self.admin_client.list_topics(timeout=timeout)
        return list(metadata.topics.keys())

    def delete_topic(self, topic_name: str, timeout: float = 10.0):
        """
        Удаляет указанный топик.

        Args:
            topic_name: Название топика.
            timeout: Таймаут операции в секундах.

        Raises:
            RuntimeError: Если топик не существует или возникла ошибка удаления.
        """
        futures = self.admin_client.delete_topics(
            [topic_name], operation_timeout=timeout
        )
        for topic, future in futures.items():
            try:
                future.result(timeout=timeout)
                self.logger.info(f"Топик '{topic}' успешно удалён.")
            except KafkaException as e:
                raise RuntimeError(
                    f"Ошибка при удалении топика '{topic}': {e}"
                )

    def add_partitions(
        self, topic_name: str, total_count: int, timeout: float = 10.0
    ):
        """
        Увеличивает количество партиций в топике до total_count.

        Если total_count меньше текущего количества, ничего не изменится.

        Args:
            topic_name: Название топика.
            total_count: Итоговое желаемое количество партиций.
            timeout: Таймаут операции в секундах.

        Raises:
            RuntimeError: Если возникла ошибка при добавлении партиций.
        """
        new_partitions = NewPartitions(topic_name, total_count)
        futures = self.admin_client.create_partitions(
            [new_partitions], operation_timeout=timeout
        )
        for topic, future in futures.items():
            try:
                future.result(timeout=timeout)
                self.logger.info(
                    f"Партиции для топика '{topic}' успешно обновлены до {total_count}."
                )
            except KafkaException as e:
                raise RuntimeError(
                    f"Ошибка при добавлении партиций для топика '{topic}': {e}"
                )

    def describe_configs(self, topic_name: str, timeout: float = 10.0) -> dict:
        """
        Получает текущую конфигурацию топика.

        Args:
            topic_name: Название топика.
            timeout: Таймаут операции в секундах.

        Returns:
            Словарь {ключ: значение} конфигураций топика.

        Raises:
            RuntimeError: Если возникла ошибка при получении конфигурации.
        """
        topic_resource = ConfigResource(ConfigResource.Type.TOPIC, topic_name)
        futures = self.admin_client.describe_configs(
            [topic_resource], request_timeout=timeout
        )
        try:
            topic_config = futures[topic_resource].result()
            config_dict = {}
            for name, config_entry in topic_config.items():
                # config_entry.value, config_entry.source, config_entry.is_read_only и т.д.
                config_dict[name] = config_entry.value
            return config_dict
        except KafkaException as e:
            raise RuntimeError(
                f"Ошибка при получении конфигурации топика '{topic_name}': {e}"
            )

    def alter_configs(
        self, topic_name: str, new_config: dict, timeout: float = 10.0
    ):
        """
        Изменяет конфигурацию заданного топика.

        Args:
            topic_name: Название топика.
            new_config: Словарь {ключ_конфигурации: значение}.
            timeout: Таймаут операции в секундах.

        Raises:
            RuntimeError: Если возникла ошибка при изменении конфигурации.
        """
        topic_resource = ConfigResource(ConfigResource.Type.TOPIC, topic_name)
        # Устанавливаем новые значения
        for k, v in new_config.items():
            topic_resource.set_config(k, v)

        futures = self.admin_client.alter_configs(
            [topic_resource], request_timeout=timeout
        )
        try:
            futures[topic_resource].result(timeout=timeout)
            self.logger.info(
                "kafka.admin.alter_config.success",
                topic=topic_name,
                config=new_config,
            )
        except KafkaException as e:
            raise RuntimeError(
                f"Ошибка при изменении конфигурации топика '{topic_name}': {e}"
            )

    def compare_topic_config(
        self, topic_name: str, expected_config: dict, timeout: float = 10.0
    ) -> dict[str, tuple[str | None, str]]:
        """
        Сравнивает текущую конфигурацию топика с ожидаемой.

        Используется для обнаружения configuration drift в миграциях.

        Args:
            topic_name: Название топика
            expected_config: Ожидаемая конфигурация
            timeout: Таймаут операции

        Returns:
            Словарь {ключ: (текущее_значение, ожидаемое_значение)}
            Пустой словарь если конфигурации совпадают

        Example:
            ```python
            diff = admin.compare_topic_config(
                'my-topic',
                {'retention.ms': '86400000', 'cleanup.policy': 'delete'}
            )
            if diff:
                print(f"Config drift detected: {diff}")
                # {'retention.ms': ('604800000', '86400000')}
            ```
        """
        current_config = self.describe_configs(topic_name, timeout)
        diff = {}

        for key, expected_value in expected_config.items():
            current_value = current_config.get(key)
            if current_value != expected_value:
                diff[key] = (current_value, expected_value)

        if diff:
            self.logger.warning(
                "kafka.admin.config_drift",
                topic=topic_name,
                drift=diff,
            )

        return diff

    def get_topic_metadata(
        self, topic_name: str, timeout: float = 10.0
    ) -> TopicMetadata:
        """
        Получает метаданные топика (партиции, реплики и т.д.).

        Args:
            topic_name: Название топика.
            timeout: Таймаут операции в секундах.

        Returns:
            TopicMetadata объект с информацией о топике.

        Raises:
            RuntimeError: Если топик не найден или ошибка получения метаданных.
        """
        metadata = self.admin_client.list_topics(
            topic=topic_name, timeout=timeout
        )
        topic_metadata = metadata.topics.get(topic_name)

        if not topic_metadata:
            raise RuntimeError(f"Топик '{topic_name}' не найден")

        return topic_metadata

    def healthcheck(self, timeout: float = 5.0) -> dict:
        """
        Проверяет доступность Kafka кластера и возвращает статус.

        Используется для мониторинга и проверки подключения.

        Args:
            timeout: Таймаут проверки в секундах

        Returns:
            Словарь со статусом:
            {
                "status": "healthy" | "unhealthy",
                "broker_count": int,
                "topics_count": int,
                "latency_ms": float,
                "error": str | None
            }

        Example:
            ```python
            health = admin.healthcheck()
            if health['status'] == 'healthy':
                print(f"Kafka OK: {health['broker_count']} brokers, "
                      f"{health['topics_count']} topics, "
                      f"latency {health['latency_ms']}ms")
            else:
                print(f"Kafka error: {health['error']}")
            ```
        """
        try:
            start = time.time()
            metadata = self.admin_client.list_topics(timeout=timeout)
            latency = (time.time() - start) * 1000

            broker_count = len(metadata.brokers)
            topics_count = len(metadata.topics)

            result = {
                "status": "healthy",
                "broker_count": broker_count,
                "topics_count": topics_count,
                "latency_ms": round(latency, 2),
                "error": None,
            }

            self.logger.info(
                "kafka.admin.healthcheck.success",
                **result,
            )

            return result

        except Exception as e:
            result = {
                "status": "unhealthy",
                "broker_count": 0,
                "topics_count": 0,
                "latency_ms": 0.0,
                "error": str(e),
            }

            self.logger.error(
                "kafka.admin.healthcheck.failed",
                error=str(e),
            )

            return result
