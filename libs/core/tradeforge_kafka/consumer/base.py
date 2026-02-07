"""
Асинхронный Kafka Consumer на основе confluent-kafka.

Использует dedicated thread pool для Kafka I/O операций,
пользовательская обработка полностью асинхронная.
"""

from __future__ import annotations

import asyncio
import json
import traceback
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

import structlog
from confluent_kafka import Consumer as ConfluentConsumer
from confluent_kafka import KafkaError, TopicPartition
from pydantic import BaseModel, ValidationError
from tradeforge_logger import get_logger

from ..config import ConsumerConfig, ProducerConfig
from ..datatypes import DLQMessage, KafkaMessage
from ..exceptions import (
    FatalError,
    MaxRetriesExceededError,
    MessageValidationError,
    RetryableError,
)
from ..metrics import ConsumerMetrics, MetricsCollector
from ..producer.base import AsyncKafkaProducer

T = TypeVar("T", bound=BaseModel)

logger = get_logger(__name__)


class AsyncKafkaConsumer(ABC, Generic[T]):
    """
    Асинхронный Kafka Consumer с:
    - Автоматической валидацией через Pydantic
    - Graceful shutdown
    - Retry logic with exponential backoff
    - Dead Letter Queue
    - Метриками и observability
    - Correlation ID для distributed tracing
    - Type safety

    Архитектура:
        1. Dedicated thread для poll() из Kafka (confluent-kafka синхронный)
        2. asyncio.Queue для передачи сообщений в async event loop
        3. Пользовательский on_message() - полностью async
        4. Manual commit после успешной обработки

    Example:
        ```python
        from pydantic import BaseModel
        from tradeforge_kafka.consumer.base import AsyncKafkaConsumer
        from tradeforge_kafka.config import ConsumerConfig

        class MyMessage(BaseModel):
            ticker: str
            timeframe: str

        class MyConsumer(AsyncKafkaConsumer[MyMessage]):
            async def on_message(self, msg: KafkaMessage[MyMessage]) -> None:
                logger.info(f"Processing {msg.value.ticker}")
                # Ваша бизнес-логика здесь

        config = ConsumerConfig(
            bootstrap_servers="localhost:9092",
            topic="my-topic",
            group_id="my-service"
        )

        async def main():
            consumer = MyConsumer(config=config, message_schema=MyMessage)
            async with consumer:
                await consumer.start()

        asyncio.run(main())
        ```
    """

    def __init__(
        self,
        config: ConsumerConfig,
        message_schema: type[T],
        metrics_collector: MetricsCollector | None = None,
        dlq_producer: Any | None = None,
    ):
        """
        Инициализация Consumer.

        Args:
            config: Конфигурация consumer
            message_schema: Pydantic модель для валидации сообщений
            metrics_collector: Опциональный коллектор метрик (для Prometheus)
            dlq_producer: Producer для отправки в DLQ (будет создан автоматически если не передан)
        """
        self.config = config
        self.message_schema = message_schema
        self.metrics_collector = metrics_collector
        self._external_dlq_producer = (
            dlq_producer  # Внешний DLQ producer (если передан)
        )
        self._internal_dlq_producer: Any | None = (
            None  # Внутренний DLQ producer (создастся при необходимости)
        )

        self.consumer: ConfluentConsumer | None = None
        self.metrics = ConsumerMetrics()

        # Внутренняя очередь для передачи сообщений из thread pool в async loop
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=config.max_poll_records
        )

        # Флаги управления жизненным циклом
        self._shutdown_event = asyncio.Event()
        self._poll_executor: ThreadPoolExecutor | None = None
        self._poll_task: asyncio.Task | None = None

        # Параллельная обработка сообщений
        self._active_tasks: set[asyncio.Task] = set()
        self._max_concurrent = config.max_concurrent_messages

        # Offset tracking для правильных коммитов при параллельной обработке
        # Структура: {(topic, partition): {offset: processing_status}}
        # processing_status: "processing" | "success" | "failed"
        self._offset_tracker: dict[tuple[str, int], dict[int, str]] = (
            defaultdict(dict)
        )
        self._offset_lock = asyncio.Lock()

        # Контекст для structlog (correlation_id)
        self._log = logger.bind(
            service=self.__class__.__name__,
            topic=config.topic,
            group_id=config.group_id,
        )

    @abstractmethod
    async def on_message(self, message: KafkaMessage[T]) -> None:
        """
        Обработка сообщения. ОБЯЗАТЕЛЬНО переопределить в наследнике.

        Args:
            message: Валидированное сообщение с типизированным value

        Raises:
            RetryableError: Временная ошибка, требуется retry
            FatalError: Постоянная ошибка, отправить в DLQ без retry
            Exception: Любая другая ошибка считается RetryableError

        Example:
            ```python
            async def on_message(self, msg: KafkaMessage[MyMessage]) -> None:
                try:
                    result = await self.external_api.call(msg.value.ticker)
                    await self.db.save(result)
                except ConnectionError as e:
                    # Временная ошибка - будет retry
                    raise RetryableError(f"API unavailable: {e}") from e
                except ValueError as e:
                    # Постоянная ошибка - сразу в DLQ
                    raise FatalError(f"Invalid data: {e}") from e
            ```
        """
        raise NotImplementedError("Метод on_message должен быть реализован")

    async def __aenter__(self) -> AsyncKafkaConsumer[T]:
        """Context manager: подключение к Kafka."""
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager: отключение от Kafka."""
        await self._disconnect()

    async def _connect(self) -> None:
        """Асинхронное подключение к Kafka и запуск poll thread."""
        self._log.info("kafka.consumer.connecting")

        # Создаем confluent-kafka Consumer
        self.consumer = ConfluentConsumer(
            {
                "bootstrap.servers": self.config.bootstrap_servers,
                "group.id": self.config.group_id,
                "auto.offset.reset": self.config.auto_offset_reset,
                "enable.auto.commit": False,  # ВСЕГДА manual commit
                "max.poll.interval.ms": self.config.max_poll_interval_ms,
                "session.timeout.ms": self.config.session_timeout_ms,
                "fetch.wait.max.ms": self.config.fetch_wait_max_ms,
            }
        )

        # Подписываемся на топик
        self.consumer.subscribe([self.config.topic])

        # Создаем thread pool для Kafka I/O (один поток)
        self._poll_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"kafka-poll-{self.config.topic}"
        )

        self._log.info(
            "kafka.consumer.connected",
            topic=self.config.topic,
            group_id=self.config.group_id,
        )

    async def _disconnect(self) -> None:
        """
        Two-Phase Graceful Shutdown с ожиданием завершения активных задач.

        Phase 1 (Soft): Позволяем задачам завершиться естественно (shutdown_soft_timeout_seconds)
        Phase 2 (Hard): Принудительно отменяем оставшиеся задачи (shutdown_hard_timeout_seconds)

        Гарантирует завершение в течение: soft_timeout + hard_timeout + overhead (~5s)
        """
        self._log.info("kafka.consumer.disconnecting")

        # Сигнализируем об остановке (новые сообщения не принимаем)
        self._shutdown_event.set()

        # Останавливаем poll task (прекращаем получать новые сообщения)
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        # ========== TWO-PHASE SHUTDOWN ДЛЯ АКТИВНЫХ ЗАДАЧ ==========

        # Phase 1: Soft Shutdown - ждем естественного завершения
        if self._active_tasks:
            active_count = len(self._active_tasks)
            self._log.info(
                "kafka.consumer.shutdown_phase1_soft",
                active_tasks=active_count,
                timeout_seconds=self.config.shutdown_soft_timeout_seconds,
            )

            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *self._active_tasks, return_exceptions=True
                    ),
                    timeout=self.config.shutdown_soft_timeout_seconds,
                )
                self._log.info(
                    "kafka.consumer.shutdown_phase1_success",
                    completed_tasks=active_count,
                )

            except asyncio.TimeoutError:
                # Phase 2: Hard Shutdown - принудительная отмена оставшихся
                remaining = [t for t in self._active_tasks if not t.done()]
                remaining_count = len(remaining)

                self._log.warning(
                    "kafka.consumer.shutdown_phase2_hard",
                    remaining_tasks=remaining_count,
                    timeout_seconds=self.config.shutdown_hard_timeout_seconds,
                )

                # Отменяем оставшиеся задачи
                for task in remaining:
                    task.cancel()

                # Даем время на cancellation
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*remaining, return_exceptions=True),
                        timeout=self.config.shutdown_hard_timeout_seconds,
                    )
                    self._log.info(
                        "kafka.consumer.shutdown_phase2_success",
                        cancelled_tasks=remaining_count,
                    )

                except asyncio.TimeoutError:
                    # Если и после hard timeout задачи не завершились - логируем критичную ошибку
                    still_running = [t for t in remaining if not t.done()]
                    self._log.error(
                        "kafka.consumer.shutdown_forced",
                        stuck_tasks=len(still_running),
                        message="Задачи не завершились даже после force cancel - возможна утечка ресурсов",
                    )

        # Закрываем consumer
        if self.consumer:
            await asyncio.to_thread(self.consumer.close)

        # Останавливаем thread pool
        if self._poll_executor:
            self._poll_executor.shutdown(wait=True)

        # Закрываем внутренний DLQ producer если он был создан
        if self._internal_dlq_producer:
            await self._internal_dlq_producer.__aexit__(None, None, None)

        self._log.info(
            "kafka.consumer.disconnected", metrics=self.metrics.to_dict()
        )

    async def start(self) -> None:
        """
        Запуск основного цикла обработки сообщений.

        Этот метод блокирующий - работает до вызова shutdown().
        """
        self._log.info("kafka.consumer.starting")

        try:
            # Запускаем poll в отдельном task
            self._poll_task = asyncio.create_task(self._poll_loop())

            # Обрабатываем сообщения из очереди
            await self._process_loop()

        except asyncio.CancelledError:
            self._log.info("kafka.consumer.cancelled")
        except Exception as e:
            self._log.error(
                "kafka.consumer.critical_error", error=str(e), exc_info=True
            )
            raise
        finally:
            self._log.info("kafka.consumer.stopped")

    async def _poll_loop(self) -> None:
        """
        Цикл poll из Kafka (выполняется в thread pool).

        Извлекает сообщения и помещает их в asyncio.Queue.
        """
        loop = asyncio.get_running_loop()

        while not self._shutdown_event.is_set():
            try:
                # Запускаем синхронный poll в thread pool
                raw_message = await loop.run_in_executor(
                    self._poll_executor,
                    self.consumer.poll,
                    self.config.poll_timeout_seconds,
                )

                if raw_message is None:
                    continue

                if raw_message.error():
                    self._handle_poll_error(raw_message.error())
                    continue

                # Помещаем в очередь для async обработки
                await self._message_queue.put(raw_message)

            except Exception as e:
                self._log.error(
                    "kafka.consumer.poll_error", error=str(e), exc_info=True
                )
                await asyncio.sleep(self.config.poll_timeout_seconds)

    def _handle_poll_error(self, error: KafkaError) -> None:
        """Обработка ошибок poll."""
        if error.code() == KafkaError._PARTITION_EOF:
            # Достигнут конец партиции - это норма
            pass
        else:
            self._log.error("kafka.consumer.kafka_error", error=str(error))

    async def _process_loop(self) -> None:
        """
        Основной цикл обработки сообщений из очереди с поддержкой параллельности.

        Если max_concurrent_messages > 1, запускает обработку сообщений параллельно
        через asyncio.create_task() с контролем количества активных задач.
        """
        while not self._shutdown_event.is_set():
            try:
                # Ждем сообщение из очереди
                raw_message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=self.config.process_loop_timeout_seconds,
                )

                # Ждем если достигнут лимит параллельных задач
                while len(self._active_tasks) >= self._max_concurrent:
                    await self._cleanup_finished_tasks()
                    # Небольшая задержка для снижения CPU нагрузки
                    await asyncio.sleep(
                        self.config.concurrent_task_sleep_ms / 1000.0
                    )

                # Создаем новую задачу для обработки сообщения
                task = asyncio.create_task(
                    self._process_message_wrapper(raw_message)
                )
                self._active_tasks.add(task)

                # Callback для автоматического удаления завершенных задач
                task.add_done_callback(self._active_tasks.discard)

            except asyncio.TimeoutError:
                # Таймаут - проверяем shutdown_event и продолжаем
                # Также чистим завершенные задачи
                await self._cleanup_finished_tasks()
                continue
            except Exception as e:
                self._log.error(
                    "kafka.consumer.process_loop_error",
                    error=str(e),
                    exc_info=True,
                )

    async def _cleanup_finished_tasks(self) -> None:
        """
        Удаляет завершенные задачи из set активных задач.

        Также собирает исключения если они были.
        """
        done_tasks = {t for t in self._active_tasks if t.done()}
        for task in done_tasks:
            try:
                # Проверяем на исключения
                task.result()
            except Exception as e:
                self._log.error(
                    "kafka.consumer.task_exception",
                    error=str(e),
                    exc_info=True,
                )
        self._active_tasks -= done_tasks

    async def _process_message_wrapper(self, raw_message: Any) -> None:
        """
        Обертка для обработки сообщения с tracking метрик параллельности.

        Args:
            raw_message: Сырое сообщение от confluent-kafka
        """
        # Отслеживаем начало обработки
        self.metrics.record_processing_started()

        try:
            await self._process_message(raw_message)
        finally:
            # Отслеживаем завершение обработки
            self.metrics.record_processing_finished()

    async def _process_message(self, raw_message: Any) -> None:
        """
        Обработка одного сообщения с валидацией, retry, метриками и offset tracking.

        Args:
            raw_message: Сырое сообщение от confluent-kafka
        """
        start_time = asyncio.get_event_loop().time()
        correlation_id = self._extract_correlation_id(raw_message)

        # Извлекаем метаданные для offset tracking
        topic = raw_message.topic()
        partition = raw_message.partition()
        offset = raw_message.offset()

        # Биндим correlation_id в structlog context
        log = self._log.bind(correlation_id=correlation_id)

        log.debug(
            "kafka.consumer.message_received",
            partition=partition,
            offset=offset,
        )

        # Помечаем офсет как обрабатываемый
        await self._mark_offset_processing(topic, partition, offset)

        # Уведомляем metrics collector
        if self.metrics_collector:
            self.metrics_collector.on_message_received(
                {"correlation_id": correlation_id}
            )

        try:
            # 1. Валидация через Pydantic
            kafka_message = self._validate_message(raw_message)

            # 2. Обработка с retry логикой
            await self._process_with_retry(kafka_message, log)

            # 3. Помечаем офсет как успешно обработанный (внутри произойдет коммит)
            await self._mark_offset_success(topic, partition, offset)

            # 4. Метрики
            processing_time_ms = (
                asyncio.get_event_loop().time() - start_time
            ) * 1000
            self.metrics.record_success(processing_time_ms)

            # Логируем медленные сообщения
            if (
                self.config.log_slow_messages
                and processing_time_ms > self.config.slow_threshold_ms
            ):
                log.warning(
                    "kafka.consumer.slow_message",
                    processing_time_ms=round(processing_time_ms, 2),
                    threshold_ms=self.config.slow_threshold_ms,
                )

            # Периодическое логирование
            if (
                self.metrics.total_processed % self.config.log_every_n_messages
                == 0
            ):
                log.info(
                    "kafka.consumer.batch_summary",
                    **self.metrics.to_dict(),
                )

            if self.metrics_collector:
                self.metrics_collector.on_message_processed(
                    {
                        "correlation_id": correlation_id,
                        "processing_time_ms": processing_time_ms,
                    },
                    success=True,
                )

        except MessageValidationError as e:
            log.error(
                "kafka.consumer.validation_error",
                error=str(e),
                raw_value=raw_message.value().decode(
                    "utf-8", errors="replace"
                ),
            )
            self.metrics.record_validation_error()

            # Коммитим через offset tracker, чтобы не зациклиться на битом сообщении
            await self._mark_offset_success(topic, partition, offset)

            if self.metrics_collector:
                self.metrics_collector.on_message_processed(
                    {"correlation_id": correlation_id}, success=False
                )

        except MaxRetriesExceededError:
            log.error(
                "kafka.consumer.max_retries_exceeded",
                max_retries=self.config.max_retries,
            )
            self.metrics.record_error()

            # Коммитим офсет через offset tracker, чтобы не блокировать очередь
            await self._mark_offset_success(topic, partition, offset)

            if self.metrics_collector:
                self.metrics_collector.on_message_processed(
                    {"correlation_id": correlation_id}, success=False
                )

        except Exception as e:
            log.exception(
                "kafka.consumer.unexpected_error",
                error=str(e),
            )
            self.metrics.record_error()

            # Помечаем как failed - НЕ коммитим
            # (сообщение вернется в очередь при следующем rebalance или перезапуске)
            await self._mark_offset_failed(topic, partition, offset)

            if self.metrics_collector:
                self.metrics_collector.on_message_processed(
                    {"correlation_id": correlation_id}, success=False
                )

    def _extract_correlation_id(self, raw_message: Any) -> str:
        """
        Извлекает или генерирует correlation_id из заголовков сообщения.

        Args:
            raw_message: Сырое сообщение от confluent-kafka

        Returns:
            Correlation ID
        """
        headers = raw_message.headers() or []
        for key, value in headers:
            if key == "X-Correlation-ID":
                return value.decode("utf-8")

        # Если нет - генерируем новый
        return str(uuid.uuid4())

    async def _mark_offset_processing(
        self, topic: str, partition: int, offset: int
    ) -> None:
        """
        Помечает офсет как находящийся в обработке.

        Args:
            topic: Название топика
            partition: Номер партиции
            offset: Офсет сообщения
        """
        async with self._offset_lock:
            key = (topic, partition)
            self._offset_tracker[key][offset] = "processing"

    def _validate_message(self, raw_message: Any) -> KafkaMessage[T]:
        """
        Валидирует сообщение через Pydantic.

        Args:
            raw_message: Сырое сообщение от confluent-kafka

        Returns:
            Валидированное KafkaMessage

        Raises:
            MessageValidationError: Если валидация не прошла
        """
        try:
            raw_value = raw_message.value().decode("utf-8")
            value_dict = json.loads(raw_value)

            # Валидируем полезную нагрузку через Pydantic
            validated_value = self.message_schema.model_validate(value_dict)

            # Извлекаем заголовки
            headers = {}
            if raw_message.headers():
                for key, value in raw_message.headers():
                    headers[key] = value.decode("utf-8")

            # Создаем KafkaMessage
            return KafkaMessage[T](
                key=(
                    raw_message.key().decode("utf-8")
                    if raw_message.key()
                    else None
                ),
                value=validated_value,
                topic=raw_message.topic(),
                partition=raw_message.partition(),
                offset=raw_message.offset(),
                timestamp=datetime.fromtimestamp(
                    raw_message.timestamp()[1] / 1000
                ),
                headers=headers,
            )

        except ValidationError as e:
            raise MessageValidationError(
                f"Pydantic validation failed: {e}"
            ) from e
        except json.JSONDecodeError as e:
            raise MessageValidationError(f"JSON decode failed: {e}") from e
        except Exception as e:
            raise MessageValidationError(
                f"Message validation failed: {e}"
            ) from e

    async def _process_with_retry(
        self, kafka_message: KafkaMessage[T], log: structlog.stdlib.BoundLogger
    ) -> None:
        """
        Обрабатывает сообщение с retry логикой.

        Args:
            kafka_message: Валидированное сообщение
            log: Logger с correlation_id

        Raises:
            MaxRetriesExceededError: Если исчерпаны попытки
        """
        last_exception: Exception | None = None
        first_attempt_at = datetime.now(UTC)

        for attempt in range(1, self.config.max_retries + 1):
            try:
                # Вызываем пользовательский обработчик
                await self.on_message(kafka_message)

                # Успех!
                return

            except FatalError as e:
                # Постоянная ошибка - сразу в DLQ без retry
                log.error(
                    "kafka.consumer.fatal_error",
                    error=str(e),
                    attempt=attempt,
                )
                await self._send_to_dlq(
                    kafka_message, e, first_attempt_at, attempt
                )
                raise MaxRetriesExceededError(str(e)) from e

            except RetryableError as e:
                last_exception = e
                log.warning(
                    "kafka.consumer.retryable_error",
                    error=str(e),
                    attempt=attempt,
                    max_retries=self.config.max_retries,
                )

            except Exception as e:
                # Любая другая ошибка считается RetryableError
                last_exception = e
                log.warning(
                    "kafka.consumer.error",
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=attempt,
                    max_retries=self.config.max_retries,
                )

            self.metrics.record_retry()

            # Если это не последняя попытка - ждем перед retry
            if attempt < self.config.max_retries:
                delay = self._get_retry_delay(attempt)
                log.info(
                    "kafka.consumer.retry_delay",
                    delay_seconds=delay,
                    next_attempt=attempt + 1,
                )
                await asyncio.sleep(delay)

        # Исчерпаны попытки - отправляем в DLQ
        if self.config.use_dlq:
            await self._send_to_dlq(
                kafka_message,
                last_exception,
                first_attempt_at,
                self.config.max_retries,
            )

        raise MaxRetriesExceededError(
            f"Max retries exceeded: {last_exception}"
        ) from last_exception

    def _get_retry_delay(self, attempt: int) -> float:
        """
        Вычисляет задержку перед retry (exponential backoff).

        Args:
            attempt: Номер попытки (1-indexed)

        Returns:
            Задержка в секундах
        """
        if attempt - 1 < len(self.config.retry_delays):
            return self.config.retry_delays[attempt - 1]

        # Если попыток больше чем в конфиге - используем последнюю задержку
        return self.config.retry_delays[-1]

    async def _get_dlq_producer(self):
        """
        Получает или создает DLQ producer.

        Returns:
            AsyncKafkaProducer для отправки в DLQ
        """
        # Если передан внешний producer - используем его
        if self._external_dlq_producer:
            return self._external_dlq_producer

        # Если внутренний producer еще не создан - создаем
        if self._internal_dlq_producer is None:
            dlq_producer_config = ProducerConfig(
                bootstrap_servers=self.config.bootstrap_servers,
                acks="all",
                compression_type="gzip",
            )

            self._internal_dlq_producer = AsyncKafkaProducer(
                dlq_producer_config
            )
            await self._internal_dlq_producer.__aenter__()

            self._log.info("kafka.consumer.dlq_producer_created")

        return self._internal_dlq_producer

    async def _send_to_dlq(
        self,
        kafka_message: KafkaMessage[T],
        exception: Exception,
        first_attempt_at: datetime,
        attempts: int,
    ) -> None:
        """
        Отправляет failed сообщение в Dead Letter Queue.

        Args:
            kafka_message: Оригинальное сообщение
            exception: Исключение, которое привело к DLQ
            first_attempt_at: Время первой попытки
            attempts: Количество попыток
        """
        if not self.config.use_dlq:
            return

        dlq_topic = f"{kafka_message.topic}{self.config.dlq_topic_suffix}"

        dlq_message = DLQMessage(
            original_message=kafka_message.model_dump(mode="json"),
            original_topic=kafka_message.topic,
            error=str(exception),
            stacktrace=traceback.format_exc(),
            attempts=attempts,
            first_attempt_at=first_attempt_at,
            last_attempt_at=datetime.now(UTC),
            correlation_id=kafka_message.correlation_id,
        )

        self._log.error(
            "kafka.consumer.sending_to_dlq",
            dlq_topic=dlq_topic,
            correlation_id=kafka_message.correlation_id,
            attempts=attempts,
            error=str(exception),
        )

        try:
            # Получаем DLQ producer
            producer = await self._get_dlq_producer()

            # Отправляем в DLQ
            await producer.send(
                topic=dlq_topic,
                message=dlq_message.model_dump(mode="json"),
                key=kafka_message.key,
                correlation_id=kafka_message.correlation_id,
            )

            self.metrics.record_dlq_sent()

            self._log.info(
                "kafka.consumer.dlq_sent",
                dlq_topic=dlq_topic,
                correlation_id=kafka_message.correlation_id,
            )

        except Exception as e:
            self._log.error(
                "kafka.consumer.dlq_send_failed",
                error=str(e),
                dlq_topic=dlq_topic,
                exc_info=True,
            )

    async def _mark_offset_success(
        self, topic: str, partition: int, offset: int
    ) -> None:
        """
        Помечает офсет как успешно обработанный и коммитит если возможно.

        АТОМАРНАЯ ОПЕРАЦИЯ: Вся логика вычисления и коммита под одним lock
        для предотвращения race condition при параллельной обработке.

        Args:
            topic: Название топика
            partition: Номер партиции
            offset: Офсет сообщения
        """
        async with self._offset_lock:
            key = (topic, partition)
            self._offset_tracker[key][offset] = "success"

            # Вычисление safe offset под lock (синхронная версия)
            safe_offset = self._get_safe_commit_offset_sync(topic, partition)
            if safe_offset is not None:
                # Коммит также остается под lock - операция полностью атомарна
                await self._commit_offset(topic, partition, safe_offset)

    async def _mark_offset_failed(
        self, topic: str, partition: int, offset: int
    ) -> None:
        """
        Помечает офсет как failed (не коммитим, но удаляем из tracking).

        Args:
            topic: Название топика
            partition: Номер партиции
            offset: Офсет сообщения
        """
        async with self._offset_lock:
            key = (topic, partition)
            self._offset_tracker[key][offset] = "failed"

    def _get_safe_commit_offset_sync(
        self, topic: str, partition: int
    ) -> int | None:
        """
        Вычисляет безопасный офсет для коммита (синхронная версия).

        ВАЖНО: Этот метод вызывается под _offset_lock, поэтому НЕ должен быть async.
        Это предотвращает race condition при параллельной обработке офсетов.

        Возвращает максимальный офсет, для которого ВСЕ предыдущие офсеты
        успешно обработаны (нет "дыр").

        Args:
            topic: Название топика
            partition: Номер партиции

        Returns:
            Безопасный офсет для коммита или None если нет
        """
        key = (topic, partition)
        offsets = self._offset_tracker.get(key, {})

        if not offsets:
            return None

        # Сортируем офсеты
        sorted_offsets = sorted(offsets.keys())

        # Находим максимальный последовательный успешный офсет
        safe_offset = None
        for offset in sorted_offsets:
            status = offsets[offset]
            if status == "success":
                safe_offset = offset
            else:
                # Встретили "дыру" (processing или failed) - останавливаемся
                break

        return safe_offset

    async def _commit_offset(
        self, topic: str, partition: int, offset: int
    ) -> None:
        """
        Коммитит офсет в Kafka.

        Args:
            topic: Название топика
            partition: Номер партиции
            offset: Офсет для коммита (следующий для чтения будет offset + 1)
        """
        try:
            tp = TopicPartition(topic, partition, offset + 1)
            await asyncio.to_thread(
                self.consumer.commit, offsets=[tp], asynchronous=False
            )

            # Чистим старые отслеженные офсеты (до закоммиченного)
            key = (topic, partition)
            offsets_to_remove = [
                o for o in self._offset_tracker[key].keys() if o <= offset
            ]
            for o in offsets_to_remove:
                del self._offset_tracker[key][o]

            self._log.debug(
                "kafka.consumer.offset_committed",
                topic=topic,
                partition=partition,
                offset=offset + 1,
            )

        except Exception as e:
            self._log.error(
                "kafka.consumer.commit_error",
                error=str(e),
                topic=topic,
                partition=partition,
                offset=offset,
            )

    async def shutdown(self) -> None:
        """Graceful shutdown. Можно вызвать извне для остановки."""
        self._log.info("kafka.consumer.shutdown_requested")
        self._shutdown_event.set()

        # Ждем завершения всех активных задач
        if self._active_tasks:
            self._log.info(
                "kafka.consumer.waiting_active_tasks",
                count=len(self._active_tasks),
            )
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
