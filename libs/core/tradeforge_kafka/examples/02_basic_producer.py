"""
Пример 2: Простой Producer для отправки сообщений.

Демонстрирует:
- Создание producer
- Отправку одиночных сообщений
- Отправку батча сообщений
- Получение метаданных о доставке
"""

import asyncio
import os

from pydantic import BaseModel, Field
from tradeforge_logger import get_logger

from tradeforge_kafka import AsyncKafkaProducer, ProducerConfig

logger = get_logger(__name__)


# 1. Определяем схему сообщения
class StockPrice(BaseModel):
    """Цена акции."""

    ticker: str = Field(..., description="Тикер акции (например, SBER)")
    price: float = Field(..., gt=0, description="Цена")
    volume: int = Field(..., ge=0, description="Объем торгов")


async def main():
    """Демонстрация работы Producer."""

    # 2. Конфигурация Producer
    config = ProducerConfig(
        bootstrap_servers=os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        ),
        acks="all",  # Максимальная надежность
        compression_type="gzip",  # Сжатие для экономии трафика
    )

    # 3. Создаем producer через context manager
    async with AsyncKafkaProducer[StockPrice](config) as producer:
        logger.info("producer_started")

        # 4. Отправка одиночного сообщения
        message = StockPrice(ticker="SBER", price=250.50, volume=1000000)

        metadata = await producer.send(
            topic="stock-prices",
            message=message,
            key="SBER",  # Ключ для партицирования
        )

        logger.info(
            "message_sent",
            partition=metadata.partition,
            offset=metadata.offset,
        )

        # 5. Отправка батча сообщений
        messages = [
            StockPrice(ticker="GAZP", price=180.25, volume=500000),
            StockPrice(ticker="LKOH", price=6500.00, volume=250000),
            StockPrice(ticker="YNDX", price=3200.50, volume=150000),
        ]

        results = await producer.send_batch(
            topic="stock-prices",
            messages=messages,
            key_fn=lambda msg: msg.ticker,  # Извлекаем ключ
        )

        logger.info("batch_sent", count=len(results))

    logger.info("producer_stopped")


if __name__ == "__main__":
    asyncio.run(main())
