"""
Пример 5: Административные операции с топиками.

Демонстрирует:
- Проверку здоровья Kafka кластера
- Создание и удаление топиков
- Изменение конфигурации топиков
- Сравнение конфигурации (для миграций)
"""

import asyncio
import os

from tradeforge_logger import get_logger

from tradeforge_kafka import AsyncKafkaAdmin

logger = get_logger(__name__)


async def main():
    """Демонстрация административных операций."""

    # 1. Создаем Admin клиент
    admin = AsyncKafkaAdmin(
        bootstrap_servers=os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
    )

    # 2. Проверка здоровья кластера
    logger.info("checking_kafka_health")
    health = await admin.healthcheck()

    if health["status"] == "healthy":
        logger.info(
            "kafka_healthy",
            brokers=health["broker_count"],
            topics=health["topics_count"],
            latency_ms=health["latency_ms"],
        )
    else:
        logger.error("kafka_unhealthy", error=health["error"])
        return

    # 3. Создание топика
    topic_name = "demo-topic"

    logger.info("creating_topic", topic=topic_name)
    await admin.create_topic(
        topic_name=topic_name,
        num_partitions=3,
        replication_factor=1,
        config={
            "cleanup.policy": "delete",
            "retention.ms": "86400000",  # 1 день
            "compression.type": "gzip",
        },
    )
    logger.info("topic_created", topic=topic_name)

    # 4. Проверка существования
    exists = await admin.topic_exists(topic_name)
    logger.info("topic_exists_check", topic=topic_name, exists=exists)

    # 5. Получение конфигурации
    config = await admin.describe_configs(topic_name)
    logger.info(
        "topic_config",
        retention_ms=config.get("retention.ms"),
        cleanup_policy=config.get("cleanup.policy"),
    )

    # 6. Сравнение конфигурации (полезно для миграций)
    expected_config = {
        "retention.ms": "86400000",
        "cleanup.policy": "delete",
    }

    diff = await admin.compare_topic_config(topic_name, expected_config)
    if diff:
        logger.warning("config_drift_detected", diff=diff)
    else:
        logger.info("config_matches_expected")

    # 7. Изменение конфигурации
    logger.info("updating_config")
    await admin.alter_configs(
        topic_name,
        {"retention.ms": "172800000"},  # Увеличиваем до 2 дней
    )
    logger.info("config_updated")

    # 8. Список всех топиков
    topics = await admin.list_topics()
    logger.info("topics_in_cluster", count=len(topics), topics=topics[:5])

    # 9. Удаление демо топика
    logger.info("deleting_topic", topic=topic_name)
    await admin.delete_topic(topic_name)
    logger.info("topic_deleted")


if __name__ == "__main__":
    asyncio.run(main())
