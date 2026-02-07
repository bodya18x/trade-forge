"""
Kafka Service для Internal API на базе tradeforge_kafka v2.0.0.

Обеспечивает надежную отправку сообщений в Kafka с поддержкой:
- Асинхронной доставки
- Retry logic
- Correlation ID для distributed tracing
- Graceful shutdown
"""

from __future__ import annotations

import uuid
from typing import Optional

from tradeforge_kafka import AsyncKafkaProducer
from tradeforge_kafka.config import ProducerConfig
from tradeforge_logger import get_logger

from app.settings import settings

log = get_logger(__name__)


class KafkaService:
    """
    Сервис для надежной отправки сообщений в Kafka через tradeforge_kafka v2.0.0.

    Attributes:
        _producer: AsyncKafkaProducer для отправки сообщений
        _config: Конфигурация producer
    """

    def __init__(self):
        """Инициализация KafkaService с конфигурацией из settings."""
        self._config = ProducerConfig(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            acks=settings.KAFKA_PRODUCER_ACKS,
            compression_type=settings.KAFKA_PRODUCER_COMPRESSION,
            batch_size=settings.KAFKA_PRODUCER_BATCH_SIZE,
            linger_ms=settings.KAFKA_PRODUCER_LINGER_MS,
        )
        self._producer: Optional[AsyncKafkaProducer] = None
        log.info(
            "kafka.service.initialized",
            broker=settings.KAFKA_BOOTSTRAP_SERVERS,
        )

    async def start(self):
        """
        Запуск producer (вызывается при старте приложения).

        Создает AsyncKafkaProducer и подключается к Kafka.
        """
        if self._producer is not None:
            log.warning("kafka.service.already_started")
            return

        self._producer = AsyncKafkaProducer(self._config)
        await self._producer.__aenter__()
        log.info("kafka.service.started")

    async def stop(self):
        """
        Остановка producer (вызывается при shutdown приложения).

        Гарантирует graceful shutdown с flush всех pending сообщений.
        """
        if self._producer is None:
            log.warning("kafka.service.not_started")
            return

        try:
            await self._producer.__aexit__(None, None, None)
            log.info("kafka.service.stopped")
        except Exception as e:
            log.error("kafka.service.stop.error", error=str(e), exc_info=True)
        finally:
            self._producer = None

    async def send_backtest_request(self, job_id: uuid.UUID):
        """
        Отправляет задачу на бэктест в Trading Engine.

        Args:
            job_id: UUID задачи на бэктест

        Raises:
            RuntimeError: Если producer не был запущен через start()
            Exception: При ошибке отправки сообщения
        """
        if self._producer is None:
            raise RuntimeError("KafkaService not started. Call start() first.")

        topic = settings.KAFKA_BACKTEST_REQUEST_TOPIC
        message = {"job_id": str(job_id)}
        key = str(job_id)
        # Используем job_id как correlation_id для tracing
        correlation_id = str(job_id)

        try:
            await self._producer.send(
                topic=topic,
                message=message,
                key=key,
                correlation_id=correlation_id,
            )
            log.debug(
                "kafka.message.sent",
                topic=topic,
                job_id=str(job_id),
                correlation_id=correlation_id,
            )
        except Exception as e:
            log.error(
                "kafka.send.failed",
                topic=topic,
                job_id=str(job_id),
                error=str(e),
                exc_info=True,
            )
            raise


# Создаем синглтон KafkaService
kafka_service = KafkaService()
