"""
Пример 1: Простой Consumer для обработки сообщений.

Демонстрирует:
- Создание consumer с Pydantic валидацией
- Обработку сообщений в on_message
- Graceful shutdown через context manager
"""

import asyncio
import os

from pydantic import BaseModel, Field
from tradeforge_logger import get_logger

# Правильный импорт из установленного пакета
from tradeforge_kafka import AsyncKafkaConsumer, ConsumerConfig, KafkaMessage

logger = get_logger(__name__)


# 1. Определяем схему сообщения
class StockPrice(BaseModel):
    """Цена акции."""

    ticker: str = Field(..., description="Тикер акции (например, SBER)")
    price: float = Field(..., gt=0, description="Цена")
    volume: int = Field(..., ge=0, description="Объем торгов")


# 2. Создаем Consumer
class StockPriceConsumer(AsyncKafkaConsumer[StockPrice]):
    """Consumer для обработки цен акций."""

    async def on_message(self, msg: KafkaMessage[StockPrice]) -> None:
        """
        Обработка сообщения о цене.

        Args:
            msg: Валидированное сообщение
        """
        logger.info(
            "stock_price_received",
            ticker=msg.value.ticker,
            price=msg.value.price,
            volume=msg.value.volume,
        )

        # Ваша бизнес-логика здесь
        # Например, сохранение в БД, отправка уведомлений и т.д.
        await asyncio.sleep(0.1)  # Симуляция работы


async def main():
    """Запуск consumer."""

    # 3. Конфигурация через переменные окружения или явно
    config = ConsumerConfig(
        bootstrap_servers=os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        ),
        topic=os.getenv("KAFKA_TOPIC", "stock-prices"),
        group_id=os.getenv("KAFKA_GROUP_ID", "stock-processor"),
    )

    # 4. Создаем и запускаем consumer
    consumer = StockPriceConsumer(config=config, message_schema=StockPrice)

    async with consumer:
        logger.info("consumer_started")
        await consumer.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("shutdown_requested")
