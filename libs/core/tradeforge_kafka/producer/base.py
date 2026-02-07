"""
Асинхронный Kafka Producer на основе confluent-kafka.

Использует thread pool для синхронных операций confluent-kafka,
предоставляя полностью асинхронный API.
"""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Generic, TypeVar

import structlog
from confluent_kafka import KafkaError
from confluent_kafka import Producer as ConfluentProducer
from pydantic import BaseModel
from tradeforge_logger import get_logger

from ..config import ProducerConfig
from ..datatypes import RecordMetadata
from ..exceptions import MessageSizeError, PublisherIllegalError, TimeoutError
from ..metrics import MetricsCollector, ProducerMetrics

T = TypeVar("T", bound=BaseModel)

logger = get_logger(__name__)


class AsyncKafkaProducer(Generic[T]):
    """
    Асинхронный Kafka Producer с:
    - Автоматической сериализацией через Pydantic
    - Retry logic
    - Метриками и observability
    - Батчингом
    - Correlation ID для distributed tracing
    - Type safety
    - Фоновым polling для обработки delivery callbacks

    Архитектура:
        1. Dedicated thread pool для синхронных операций confluent-kafka
        2. Фоновая задача для непрерывного polling callbacks
        3. Автоматическая сериализация Pydantic моделей в JSON
        4. Callback для отслеживания успешности доставки
        5. Асинхронные методы для удобства использования

    Example:
        ```python
        from pydantic import BaseModel
        from tradeforge_kafka.producer.base import AsyncKafkaProducer
        from tradeforge_kafka.config import ProducerConfig

        class MyMessage(BaseModel):
            ticker: str
            price: float

        config = ProducerConfig(
            bootstrap_servers="localhost:9092",
            acks="all",
            compression_type="gzip"
        )

        async def main():
            async with AsyncKafkaProducer[MyMessage](config) as producer:
                metadata = await producer.send(
                    topic="prices",
                    message=MyMessage(ticker="SBER", price=250.0),
                    key="SBER"
                )
                print(f"Sent to partition {metadata.partition}")

        asyncio.run(main())
        ```
    """

    def __init__(
        self,
        config: ProducerConfig,
        metrics_collector: MetricsCollector | None = None,
    ):
        """
        Инициализация Producer.

        Args:
            config: Конфигурация producer
            metrics_collector: Опциональный коллектор метрик (для Prometheus)
        """
        self.config = config
        self.metrics_collector = metrics_collector

        self.producer: ConfluentProducer | None = None
        self.metrics = ProducerMetrics()

        # Thread pool для синхронных операций
        self._executor: ThreadPoolExecutor | None = None

        # Для отслеживания pending callbacks
        self._pending_futures: dict[str, asyncio.Future] = {}

        # Фоновая задача для polling
        self._poll_task: asyncio.Task | None = None
        self._shutdown = False

        self._log = logger.bind(service=self.__class__.__name__)

    async def __aenter__(self) -> AsyncKafkaProducer[T]:
        """Context manager: подключение к Kafka."""
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager: отключение от Kafka."""
        await self._disconnect()

    async def _connect(self) -> None:
        """Асинхронное подключение к Kafka."""
        self._log.info("kafka.producer.connecting")

        # Создаем confluent-kafka Producer
        self.producer = ConfluentProducer(
            {
                "bootstrap.servers": self.config.bootstrap_servers,
                "acks": self.config.acks,
                "retries": self.config.retries,
                "compression.type": self.config.compression_type,
                "batch.size": self.config.batch_size,
                "linger.ms": self.config.linger_ms,
                "queue.buffering.max.kbytes": self.config.buffer_memory,
                "max.in.flight.requests.per.connection": self.config.max_in_flight_requests_per_connection,
                "request.timeout.ms": self.config.request_timeout_ms,
                "delivery.timeout.ms": self.config.delivery_timeout_ms,
            }
        )

        # Thread pool для flush и других операций
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="kafka-producer"
        )

        # Запускаем фоновый polling
        self._shutdown = False
        self._poll_task = asyncio.create_task(self._poll_loop())

        self._log.info("kafka.producer.connected")

    async def _poll_loop(self) -> None:
        """
        Фоновый loop для непрерывной обработки delivery callbacks.

        Этот loop непрерывно вызывает producer.poll() для обработки
        событий доставки сообщений. Работает в отдельной asyncio задаче.
        """
        self._log.debug("kafka.producer.poll_loop_started")

        try:
            while not self._shutdown:
                # Вызываем poll для обработки delivery callbacks
                await asyncio.to_thread(
                    self.producer.poll, self.config.poll_interval_seconds
                )

                # Небольшая пауза между итерациями для снижения CPU нагрузки
                await asyncio.sleep(self.config.poll_sleep_seconds)

        except asyncio.CancelledError:
            self._log.debug("kafka.producer.poll_loop_cancelled")
            raise
        except Exception as e:
            self._log.error("kafka.producer.poll_loop_error", error=str(e))
        finally:
            self._log.debug("kafka.producer.poll_loop_stopped")

    async def _disconnect(self) -> None:
        """Graceful shutdown с flush всех pending сообщений."""
        self._log.info("kafka.producer.disconnecting")

        # Останавливаем poll loop
        self._shutdown = True
        if self._poll_task:
            try:
                await asyncio.wait_for(
                    self._poll_task,
                    timeout=self.config.shutdown_poll_timeout_seconds,
                )
            except asyncio.TimeoutError:
                self._log.warning("kafka.producer.poll_loop_timeout")
                self._poll_task.cancel()
                try:
                    await self._poll_task
                except asyncio.CancelledError:
                    pass

        # Ждем завершения всех pending futures
        if self._pending_futures:
            self._log.info(
                "kafka.producer.waiting_pending",
                pending_count=len(self._pending_futures),
            )
            await asyncio.gather(
                *self._pending_futures.values(), return_exceptions=True
            )

        # Flush producer
        if self.producer:
            await asyncio.to_thread(
                self.producer.flush,
                timeout=self.config.shutdown_flush_timeout_seconds,
            )

        # Останавливаем executor
        if self._executor:
            self._executor.shutdown(wait=True)

        self._log.info(
            "kafka.producer.disconnected", metrics=self.metrics.to_dict()
        )

    async def send(
        self,
        topic: str,
        message: T | dict[str, Any],
        key: str | None = None,
        partition: int | None = None,
        headers: dict[str, str] | None = None,
        correlation_id: str | None = None,
    ) -> RecordMetadata:
        """
        Отправляет сообщение в Kafka.

        Args:
            topic: Топик назначения
            message: Pydantic модель или dict для отправки
            key: Ключ для определения партиции (опционально)
            partition: Явная партиция (опционально)
            headers: Дополнительные заголовки (опционально)
            correlation_id: Correlation ID для трейсинга (генерируется автоматически если не указан)

        Returns:
            RecordMetadata: Метаданные отправленного сообщения

        Raises:
            KafkaException: При ошибке отправки
            MessageSizeError: Если сообщение слишком большое
            TimeoutError: Если таймаут доставки

        Example:
            ```python
            metadata = await producer.send(
                topic="my-topic",
                message=MyMessage(data="hello"),
                key="key1",
                correlation_id="abc-123"
            )
            ```
        """
        start_time = asyncio.get_event_loop().time()

        # Генерируем correlation_id если не передан
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        # Подготавливаем headers
        final_headers = headers or {}
        final_headers["X-Correlation-ID"] = correlation_id

        log = self._log.bind(
            topic=topic, key=key, correlation_id=correlation_id
        )

        log.debug("kafka.producer.sending")

        try:
            # Сериализуем сообщение
            if isinstance(message, BaseModel):
                value_bytes = message.model_dump_json().encode("utf-8")
            elif isinstance(message, dict):
                import json

                value_bytes = json.dumps(message).encode("utf-8")
            else:
                raise TypeError(
                    f"Message must be BaseModel or dict, got {type(message)}"
                )

            key_bytes = key.encode("utf-8") if key else None

            # Конвертируем headers в байты
            headers_bytes = [
                (k, v.encode("utf-8")) for k, v in final_headers.items()
            ]

            # Создаем Future для отслеживания результата
            future_id = str(uuid.uuid4())
            result_future: asyncio.Future[RecordMetadata] = (
                asyncio.get_event_loop().create_future()
            )
            self._pending_futures[future_id] = result_future

            # Формируем kwargs динамически
            produce_kwargs = {
                "topic": topic,
                "value": value_bytes,
                "key": key_bytes,
                "headers": headers_bytes,
                "on_delivery": self._create_delivery_callback(
                    future_id, result_future, log
                ),
            }

            # Добавляем partition только если он задан
            if partition is not None:
                produce_kwargs["partition"] = partition

            # Отправляем в Kafka (неблокирующая операция)
            await asyncio.to_thread(
                self.producer.produce,
                **produce_kwargs,
            )

            # НЕ нужно вызывать poll() здесь!
            # Это делает фоновая задача _poll_loop()

            # Ждем результата доставки
            metadata = await result_future

            # Метрики
            send_time_ms = (
                asyncio.get_event_loop().time() - start_time
            ) * 1000
            self.metrics.record_success(send_time_ms)

            log.debug(
                "kafka.producer.sent",
                partition=metadata.partition,
                offset=metadata.offset,
                send_time_ms=round(send_time_ms, 2),
            )

            if self.metrics_collector:
                self.metrics_collector.on_message_sent(
                    {
                        "topic": topic,
                        "correlation_id": correlation_id,
                        "send_time_ms": send_time_ms,
                    },
                    success=True,
                )

            return metadata

        except Exception as e:
            self.metrics.record_error()
            log.error("kafka.producer.send_failed", error=str(e))

            if self.metrics_collector:
                self.metrics_collector.on_message_sent(
                    {"topic": topic, "correlation_id": correlation_id},
                    success=False,
                )

            # Удаляем future из pending
            self._pending_futures.pop(future_id, None)

            raise

    def _create_delivery_callback(
        self,
        future_id: str,
        result_future: asyncio.Future[RecordMetadata],
        log: structlog.stdlib.BoundLogger,
    ) -> Callable:
        """
        Создает callback для confluent-kafka producer.

        Args:
            future_id: ID future для удаления из pending
            result_future: asyncio.Future для установки результата
            log: Logger с контекстом

        Returns:
            Callback функция
        """

        def callback(err, msg):
            """Callback вызывается из thread pool confluent-kafka."""
            try:
                if err is not None:
                    # Ошибка доставки
                    exception = self._map_kafka_error(err)
                    log.error(
                        "kafka.producer.delivery_failed",
                        error=str(err),
                        error_code=err.code(),
                    )

                    # Устанавливаем исключение в future
                    if not result_future.done():
                        result_future.get_loop().call_soon_threadsafe(
                            result_future.set_exception, exception
                        )
                else:
                    # Успешная доставка
                    metadata = RecordMetadata(
                        topic=msg.topic(),
                        partition=msg.partition(),
                        offset=msg.offset(),
                        timestamp=(
                            datetime.fromtimestamp(msg.timestamp()[1] / 1000)
                            if msg.timestamp()[1] > 0
                            else None
                        ),
                    )

                    # Устанавливаем результат в future
                    if not result_future.done():
                        result_future.get_loop().call_soon_threadsafe(
                            result_future.set_result, metadata
                        )

            finally:
                # Удаляем из pending
                self._pending_futures.pop(future_id, None)

        return callback

    def _map_kafka_error(self, error: KafkaError) -> Exception:
        """
        Преобразует KafkaError в специфичное исключение.

        Args:
            error: KafkaError от confluent-kafka

        Returns:
            Соответствующее исключение
        """
        error_code = error.code()

        if error_code == KafkaError.MSG_SIZE_TOO_LARGE:
            return MessageSizeError(f"Message size too large: {error}")
        elif error_code == KafkaError._TIMED_OUT:
            return TimeoutError(f"Producer timeout: {error}")
        else:
            return PublisherIllegalError(f"Kafka producer error: {error}")

    async def send_batch(
        self,
        topic: str,
        messages: list[T] | list[dict[str, Any]],
        key_fn: Callable[[T], str] | None = None,
        correlation_id: str | None = None,
    ) -> list[RecordMetadata]:
        """
        Отправляет батч сообщений.

        Args:
            topic: Топик назначения
            messages: Список Pydantic моделей или dict
            key_fn: Функция для извлечения ключа из модели (опционально)
            correlation_id: Correlation ID для всего батча

        Returns:
            Список RecordMetadata для каждого сообщения

        Example:
            ```python
            messages = [
                MyMessage(ticker="SBER", price=250.0),
                MyMessage(ticker="GAZP", price=180.0),
            ]

            results = await producer.send_batch(
                topic="prices",
                messages=messages,
                key_fn=lambda msg: msg.ticker
            )
            ```
        """
        # Генерируем общий correlation_id для батча
        batch_correlation_id = correlation_id or str(uuid.uuid4())

        self._log.info(
            "kafka.producer.sending_batch",
            topic=topic,
            batch_size=len(messages),
            correlation_id=batch_correlation_id,
        )

        # Отправляем все сообщения параллельно
        tasks = [
            self.send(
                topic=topic,
                message=msg,
                key=(
                    key_fn(msg)
                    if key_fn and isinstance(msg, BaseModel)
                    else None
                ),
                correlation_id=f"{batch_correlation_id}-{i}",
            )
            for i, msg in enumerate(messages)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=False)

        self._log.info(
            "kafka.producer.batch_sent",
            topic=topic,
            batch_size=len(messages),
            correlation_id=batch_correlation_id,
        )

        return results

    async def flush(self, timeout: float = 10.0) -> int:
        """
        Ждет завершения отправки всех pending сообщений.

        Args:
            timeout: Таймаут в секундах

        Returns:
            Количество сообщений, которые не были доставлены

        Example:
            ```python
            remaining = await producer.flush(timeout=5.0)
            if remaining > 0:
                logger.warning(f"{remaining} messages not delivered")
            ```
        """
        self._log.debug("kafka.producer.flushing", timeout=timeout)

        remaining = await asyncio.to_thread(self.producer.flush, timeout)

        self._log.debug("kafka.producer.flushed", remaining=remaining)

        return remaining
