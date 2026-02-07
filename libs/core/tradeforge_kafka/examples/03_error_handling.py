"""
Пример 3: Обработка ошибок с Retry и DLQ.

Демонстрирует:
- RetryableError для временных ошибок (retry с exponential backoff)
- FatalError для постоянных ошибок (сразу в DLQ)
- Использование декораторов (timeout, circuit_breaker)
"""

import asyncio
import os

from pydantic import BaseModel, Field
from tradeforge_logger import get_logger

from tradeforge_kafka import (
    AsyncKafkaConsumer,
    ConsumerConfig,
    FatalError,
    KafkaMessage,
    RetryableError,
    circuit_breaker,
    timeout,
)

logger = get_logger(__name__)


# 1. Схема сообщения
class Order(BaseModel):
    """Торговый заказ."""

    order_id: str
    ticker: str
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)


# 2. Consumer с обработкой ошибок
class OrderProcessor(AsyncKafkaConsumer[Order]):
    """Consumer с демонстрацией error handling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts = {}  # Счетчик попыток для демо

    @timeout(10.0)  # Максимум 10 секунд на обработку
    @circuit_breaker(failure_threshold=5, recovery_timeout=30.0)
    async def on_message(self, msg: KafkaMessage[Order]) -> None:
        """
        Обработка заказа с разными сценариями ошибок.

        Args:
            msg: Сообщение с заказом
        """
        order = msg.value
        order_id = order.order_id

        logger.info("processing_order", order_id=order_id)

        # Симуляция разных сценариев на основе order_id
        if "fatal" in order_id.lower():
            # Постоянная ошибка - сразу в DLQ без retry
            raise FatalError(f"Invalid order data: {order_id}")

        elif "retry" in order_id.lower():
            # Временная ошибка - будет retry
            attempt = self.attempts.get(order_id, 0) + 1
            self.attempts[order_id] = attempt

            if attempt < 3:
                logger.warning(
                    "retrying_order", order_id=order_id, attempt=attempt
                )
                raise RetryableError(
                    f"External API unavailable (attempt {attempt})"
                )
            else:
                # После 3 попыток - успех
                del self.attempts[order_id]
                await self._process_order(order)

        else:
            # Обычная успешная обработка
            await self._process_order(order)

    async def _process_order(self, order: Order) -> None:
        """Успешная обработка заказа."""
        await asyncio.sleep(0.1)
        logger.info(
            "order_processed", order_id=order.order_id, ticker=order.ticker
        )


async def main():
    """Запуск consumer с error handling."""

    config = ConsumerConfig(
        bootstrap_servers=os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        ),
        topic=os.getenv("KAFKA_TOPIC", "orders"),
        group_id=os.getenv("KAFKA_GROUP_ID", "order-processor"),
        # Retry настройки
        max_retries=3,
        retry_delays=[1.0, 2.0, 5.0],  # Exponential backoff
        # DLQ настройки
        use_dlq=True,
        dlq_topic_suffix=".failed",  # orders.failed
    )

    consumer = OrderProcessor(config=config, message_schema=Order)

    async with consumer:
        logger.info("consumer_started")
        await consumer.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
