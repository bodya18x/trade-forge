"""
Универсальный Consumer для сбора данных.

Получает задачи из Kafka и роутит их на обработчики через TaskRegistry.
"""

from __future__ import annotations

from tradeforge_kafka import (
    AsyncKafkaConsumer,
    AsyncKafkaProducer,
    ConsumerConfig,
    KafkaMessage,
)
from tradeforge_kafka.exceptions import FatalError, RetryableError
from tradeforge_logger import get_logger, set_correlation_id

from models import CollectionTaskMessage
from modules import TaskRegistry

logger = get_logger(__name__)


class CollectionConsumer(AsyncKafkaConsumer[CollectionTaskMessage]):
    """
    Универсальный consumer для сбора данных с MOEX.

    Использует TaskRegistry для роутинга задач на нужные обработчики.
    Поддерживает параллельную обработку (max_concurrent_messages).
    """

    def __init__(
        self,
        config: ConsumerConfig,
        registry: TaskRegistry,
        producer: AsyncKafkaProducer,
        tasks_topic: str,
    ):
        """
        Инициализация consumer.

        Args:
            config: ConsumerConfig
            registry: Task registry с зарегистрированными обработчиками
            producer: Producer для реплубликации задач
            tasks_topic: Топик для отправки задач
        """
        super().__init__(
            config=config,
            message_schema=CollectionTaskMessage,
        )

        self.registry = registry
        self.producer = producer
        self.tasks_topic = tasks_topic

    async def on_message(
        self, message: KafkaMessage[CollectionTaskMessage]
    ) -> None:
        """
        Обработка задачи на сбор данных.

        Args:
            message: Kafka сообщение с валидированной задачей

        Raises:
            FatalError: При критичной ошибке (unknown task_type)
            RetryableError: При временной ошибке (MOEX API недоступен)
        """
        set_correlation_id(message.correlation_id)

        task = message.value
        task_type = task.task_type
        ticker = task.ticker
        params = task.params

        log = logger.bind(
            task_type=task_type,
            ticker=ticker,
            params=params,
            correlation_id=message.correlation_id,
        )

        log.info("collection_consumer.task_received")

        try:
            # Выполняем задачу через registry
            result = await self.registry.execute(
                task_type=task_type,
                ticker=ticker,
                params=params,
            )

            log.info(
                "collection_consumer.task_completed",
                result=result,
            )

            # Если обработчик вернул > 0 - есть еще данные
            # Реплублишим задачу для продолжения сбора
            if result > 0:
                log.info(
                    "collection_consumer.republishing_task",
                    remaining_count=result,
                )

                await self.producer.send(
                    topic=self.tasks_topic,
                    message=task,
                    key=f"{ticker}:{task_type}",
                    correlation_id=message.correlation_id,
                )

                log.info("collection_consumer.task_republished")

        except ValueError as e:
            # Unknown task_type - fatal error
            log.error(
                "collection_consumer.unknown_task_type",
                error=str(e),
                available_types=self.registry.get_registered_types(),
            )
            raise FatalError(f"Unknown task_type: {task_type}") from e

        except KeyError as e:
            # Invalid parameters (например, timeframe) - fatal error
            log.error(
                "collection_consumer.invalid_parameters",
                error=str(e),
            )
            raise FatalError(f"Invalid parameters: {e}") from e

        except Exception as e:
            # Любая другая ошибка - retryable
            log.error(
                "collection_consumer.processing_error",
                error=str(e),
                exc_info=True,
            )
            raise RetryableError(f"Processing failed: {e}") from e
