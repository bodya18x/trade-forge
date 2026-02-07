"""
RT Consumer - обработчик real-time свечей (ЗАГОТОВКА).

См. TODO.md #1 - Real-Time Trading Processor.
Запланировано к реализации после завершения MVP бэктестов.

Будет получать "жирные" свечи с индикаторами, пропускать через
активные стратегии и генерировать торговые приказы.
"""

from __future__ import annotations

from tradeforge_kafka import AsyncKafkaConsumer, KafkaMessage
from tradeforge_logger import get_logger, set_correlation_id

from models.kafka_messages import FatCandleMessage

logger = get_logger(__name__)


class RTConsumer(AsyncKafkaConsumer[FatCandleMessage]):
    """
    Consumer для обработки real-time свечей.

    Полная реализация запланирована (см. TODO.md #1):
    1. Получение "жирной" свечи с индикаторами
    2. Загрузка активных стратегий из PostgreSQL
    3. Оценка условий входа/выхода для каждой стратегии
    4. Управление открытыми позициями (Redis state)
    5. Генерация торговых приказов
    6. Отправка приказов в Kafka топик

    Attributes:
        postgres_repo: Репозиторий PostgreSQL.
        redis_client: Redis клиент для состояния позиций.
        producer: Kafka producer для торговых приказов.
    """

    def __init__(self, config):
        """
        Инициализирует RT consumer.

        Args:
            config: Конфигурация Kafka consumer.
        """
        super().__init__(config)
        logger.info("rt_consumer.initialized")

    async def on_message(
        self, message: KafkaMessage[FatCandleMessage]
    ) -> None:
        """
        Обрабатывает "жирную" свечу с индикаторами.

        Текущая реализация - заглушка. См. TODO.md #1.

        Args:
            message: Kafka сообщение с FatCandleMessage.
        """
        set_correlation_id(message.correlation_id)

        logger.debug(
            "rt_consumer.message_received",
            ticker=message.value.ticker,
            timeframe=message.value.timeframe,
            begin=message.value.begin.isoformat(),
        )

        # Заглушка. Запланировано к реализации (см. TODO.md #1):
        # 1. Загрузить активные стратегии для данного тикера
        # 2. Оценить условия входа/выхода
        # 3. Проверить открытые позиции (Redis)
        # 4. Сгенерировать торговые приказы
        # 5. Отправить приказы в Kafka

        logger.warning(
            "rt_consumer.not_implemented",
            ticker=message.value.ticker,
        )
