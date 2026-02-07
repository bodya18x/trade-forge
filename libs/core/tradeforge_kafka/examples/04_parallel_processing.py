"""
Пример 4: Параллельная обработка сообщений.

Демонстрирует:
- Параллельную обработку до N сообщений одновременно
- Правильный offset tracking при параллелизме
- Мониторинг метрик (throughput, concurrent processing)
"""

import asyncio
import os

from pydantic import BaseModel
from tradeforge_logger import get_logger

from tradeforge_kafka import AsyncKafkaConsumer, ConsumerConfig, KafkaMessage

logger = get_logger(__name__)


# 1. Схема сообщения
class DataPoint(BaseModel):
    """Точка данных для анализа."""

    id: str
    value: float
    timestamp: int


# 2. Consumer с параллельной обработкой
class ParallelProcessor(AsyncKafkaConsumer[DataPoint]):
    """Consumer обрабатывающий до 10 сообщений одновременно."""

    async def on_message(self, msg: KafkaMessage[DataPoint]) -> None:
        """
        Обработка точки данных.

        Симулирует медленную обработку (например, ML inference, внешний API).
        """
        data = msg.value
        logger.info("processing_started", id=data.id, partition=msg.partition)

        # Симуляция тяжелой обработки (например, вызов external API)
        await asyncio.sleep(2.0)  # 2 секунды на сообщение

        logger.info("processing_finished", id=data.id)


async def main():
    """Запуск consumer с параллельной обработкой."""

    config = ConsumerConfig(
        bootstrap_servers=os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        ),
        topic=os.getenv("KAFKA_TOPIC", "data-stream"),
        group_id=os.getenv("KAFKA_GROUP_ID", "parallel-processor"),
        # Параллельная обработка
        max_concurrent_messages=10,  # До 10 сообщений одновременно
        max_poll_records=50,  # Читаем по 50 за раз
    )

    consumer = ParallelProcessor(config=config, message_schema=DataPoint)

    async with consumer:
        logger.info(
            "consumer_started", max_concurrent=config.max_concurrent_messages
        )

        # Фоновая задача для логирования метрик
        async def log_metrics():
            """Периодически логирует метрики производительности."""
            while True:
                await asyncio.sleep(5)
                metrics = consumer.metrics.to_dict()
                logger.info(
                    "metrics",
                    processed=metrics["total_processed"],
                    throughput=metrics["throughput_msg_per_sec"],
                    current_processing=metrics["current_processing"],
                    max_concurrent=metrics["max_concurrent_reached"],
                    avg_time=metrics["avg_processing_time_ms"],
                )

        metrics_task = asyncio.create_task(log_metrics())

        try:
            await consumer.start()
        finally:
            metrics_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
