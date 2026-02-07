"""
Batch индикаторный consumer.

Обрабатывает задачи на расчет индикаторов для бэктестов,
выполняет расчет и отправляет результат обратно в Trading Engine.
"""

from __future__ import annotations

import asyncio

from tradeforge_kafka import (
    AsyncKafkaConsumer,
    AsyncKafkaProducer,
    KafkaMessage,
)
from tradeforge_kafka.config import ConsumerConfig
from tradeforge_kafka.consumer.decorators import log_execution_time, timeout
from tradeforge_kafka.exceptions import (
    FatalError,
    MaxRetriesExceededError,
    RetryableError,
)
from tradeforge_logger import get_logger, set_correlation_id

from core.protocols import ILockManager, IStorageManager
from models.kafka_messages import (
    BatchCalculationRequestMessage,
    BatchCalculationResponseMessage,
)
from modules.services import BatchOrchestrator
from settings import settings

logger = get_logger(__name__)


class BatchIndicatorConsumer(
    AsyncKafkaConsumer[BatchCalculationRequestMessage]
):
    """
    Batch consumer для расчета индикаторов для бэктестов.

    Архитектура:
    1. Получает задачу с параметрами (ticker, timeframe, период, индикаторы)
    2. Загружает базовые свечи из ClickHouse
    3. Рассчитывает требуемые индикаторы
    4. Сохраняет результаты с distributed lock
    5. Отправляет уведомление о завершении в Trading Engine

    Attributes:
        storage: Менеджер хранилища данных.
        locks: Менеджер распределенных блокировок.
        processing_service: Сервисный слой для обработки задач.
        producer: Producer для отправки результатов.
    """

    def __init__(
        self,
        config: ConsumerConfig,
        producer: AsyncKafkaProducer,
        storage_manager: IStorageManager,
        lock_manager: ILockManager,
        ch_client_pool: asyncio.Queue,
    ):
        """
        Инициализирует Batch consumer.

        Args:
            config: Конфигурация consumer.
            producer: Producer для отправки результатов.
            storage_manager: Менеджер хранилища.
            lock_manager: Менеджер блокировок.
            ch_client_pool: Очередь с доступными клиентами Clickhouse.
        """
        super().__init__(
            config=config,
            message_schema=BatchCalculationRequestMessage,
        )

        self.storage = storage_manager
        self.locks = lock_manager
        self.ch_client_pool = ch_client_pool
        self.processing_service = BatchOrchestrator(
            storage_manager, lock_manager
        )
        self.producer = producer

    @timeout(600.0)
    @log_execution_time(threshold_ms=10000)
    async def on_message(
        self, message: KafkaMessage[BatchCalculationRequestMessage]
    ) -> None:
        """
        Обрабатывает batch-задачу на расчет индикаторов.

        Args:
            message: Kafka сообщение с валидированной задачей.

        Raises:
            FatalError: При критичной ошибке (невалидные параметры).
            RetryableError: При временной ошибке (ClickHouse недоступен).
        """
        set_correlation_id(message.correlation_id)

        task = message.value
        job_id = task.job_id

        logger.info(
            "batch_consumer.task_started",
            job_id=job_id,
            ticker=task.ticker,
            timeframe=task.timeframe,
        )

        client = None
        try:
            client = await self.ch_client_pool.get()
            await self.processing_service.process_task(
                task.model_dump(),
                client,
                message.correlation_id,
            )

            logger.info("batch_consumer.task_completed", job_id=job_id)

            await self._send_success_notification(
                job_id, message.correlation_id
            )

        except ValueError as e:
            logger.error(
                "batch_consumer.validation_error",
                job_id=job_id,
                error=str(e),
            )

            await self._send_failure_notification(
                job_id, str(e), message.correlation_id
            )

            raise FatalError(f"Invalid task data: {e}") from e

        except RetryableError as e:
            logger.warning(
                "batch_consumer.retryable_error",
                job_id=job_id,
                error=str(e),
            )
            raise

        except FatalError as e:
            logger.error(
                "batch_consumer.fatal_error",
                job_id=job_id,
                error=str(e),
            )

            await self._send_failure_notification(
                job_id, str(e), message.correlation_id
            )
            raise

        except MaxRetriesExceededError as e:
            logger.error(
                "batch_consumer.max_retries_exceeded",
                job_id=job_id,
                error=str(e),
                max_retries=self.config.max_retries,
            )

            await self._send_failure_notification(
                job_id, str(e), message.correlation_id
            )

        except Exception as e:
            logger.exception(
                "batch_consumer.unexpected_error",
                job_id=job_id,
                error=str(e),
            )
            raise RetryableError(f"Unexpected error: {e}") from e
        finally:
            if client:
                await self.ch_client_pool.put(client)
                logger.debug("batch_orchestrator.client_returned_to_pool")

    async def _send_success_notification(
        self, job_id: str, correlation_id: str | None
    ) -> None:
        """
        Отправляет уведомление об успешном завершении задачи.

        Args:
            job_id: ID задачи.
            correlation_id: Correlation ID для трейсинга.
        """
        success_response = BatchCalculationResponseMessage(
            job_id=job_id,
            status="CALCULATION_SUCCESS",
        )

        try:
            await self.producer.send(
                topic=settings.KAFKA_BACKTESTS_TOPIC,
                message=success_response,
                key=job_id,
                correlation_id=correlation_id,
            )

            logger.info(
                "batch_consumer.success_notification_sent",
                job_id=job_id,
            )

        except Exception as e:
            logger.error(
                "batch_consumer.success_notification_failed",
                job_id=job_id,
                error=str(e),
            )
            raise RetryableError(
                f"Failed to send success notification: {e}"
            ) from e

    async def _send_failure_notification(
        self, job_id: str, error: str, correlation_id: str | None
    ) -> None:
        """
        Отправляет уведомление о failure задачи.

        Args:
            job_id: ID задачи.
            error: Описание ошибки.
            correlation_id: Correlation ID для трейсинга.
        """
        failure_response = BatchCalculationResponseMessage(
            job_id=job_id,
            status="CALCULATION_FAILURE",
            error=error,
        )

        try:
            await self.producer.send(
                topic=settings.KAFKA_BACKTESTS_TOPIC,
                message=failure_response,
                key=job_id,
                correlation_id=correlation_id,
            )

            logger.info(
                "batch_consumer.failure_notification_sent",
                job_id=job_id,
            )

        except Exception as e:
            logger.error(
                "batch_consumer.failure_notification_failed",
                job_id=job_id,
                error=str(e),
            )
