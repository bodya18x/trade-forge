"""
Backtest Consumer - обработчик задач на бэктест.

Получает задачи из Kafka, координирует процесс через Orchestrator.
"""

from __future__ import annotations

import asyncio

from clickhouse_connect.driver.exceptions import ClickHouseError
from tradeforge_kafka import (
    AsyncKafkaConsumer,
    AsyncKafkaProducer,
    KafkaMessage,
)
from tradeforge_kafka.consumer.decorators import log_execution_time, timeout
from tradeforge_kafka.exceptions import FatalError, RetryableError
from tradeforge_logger import get_logger, set_correlation_id

from core import BACKTEST_TIMEOUT_SECONDS, BacktestOrchestrator
from core.common import BacktestExecutionError
from models.kafka_messages import BacktestRequestMessage
from repositories.clickhouse import ClickHouseClientPool, ClickHouseRepository
from repositories.postgres import (
    BacktestRepository,
    IndicatorRepository,
    TickerRepository,
)

logger = get_logger(__name__)


class BacktestConsumer(AsyncKafkaConsumer[BacktestRequestMessage]):
    """
    Consumer для обработки задач на бэктест.

    Получает сообщения из Kafka, использует Orchestrator для координации
    всего процесса бэктестинга, включая запрос недостающих индикаторов.

    Attributes:
        ch_client_pool: Пул ClickHouse клиентов.
        backtest_repo: Репозиторий для BacktestJobs и BacktestResults.
        ticker_repo: Репозиторий для Tickers.
        indicator_repo: Репозиторий для индикаторов.
        clickhouse_repo: Репозиторий ClickHouse.
        producer: Kafka producer для запросов индикаторов.
        orchestrator: Orchestrator для координации бэктеста.
    """

    def __init__(
        self,
        config,
        ch_client_pool: ClickHouseClientPool,
        producer: AsyncKafkaProducer,
        backtest_repo: BacktestRepository,
        ticker_repo: TickerRepository,
        indicator_repo: IndicatorRepository,
        clickhouse_repo: ClickHouseRepository,
    ):
        """
        Инициализирует consumer с инжектированными зависимостями (DI).

        Args:
            config: Конфигурация Kafka consumer.
            ch_client_pool: Пул ClickHouse клиентов.
            producer: Kafka producer.
            backtest_repo: Репозиторий BacktestJobs и BacktestResults (injected).
            ticker_repo: Репозиторий Tickers (injected).
            indicator_repo: Репозиторий индикаторов (injected).
            clickhouse_repo: Репозиторий ClickHouse (injected).
        """
        super().__init__(config, message_schema=BacktestRequestMessage)
        self.ch_client_pool = ch_client_pool
        self.producer = producer

        # Dependency Injection - принимаем готовые репозитории
        self.backtest_repo = backtest_repo
        self.ticker_repo = ticker_repo
        self.indicator_repo = indicator_repo
        self.clickhouse_repo = clickhouse_repo

        # Создаем orchestrator с инжектированными репозиториями
        self.orchestrator = BacktestOrchestrator(
            backtest_repo=self.backtest_repo,
            ticker_repo=self.ticker_repo,
            indicator_repo=self.indicator_repo,
            clickhouse_repo=self.clickhouse_repo,
            producer=self.producer,
        )

    @timeout(BACKTEST_TIMEOUT_SECONDS)
    @log_execution_time(threshold_ms=15000)  # Логировать если > 15 секунд
    async def on_message(
        self, message: KafkaMessage[BacktestRequestMessage]
    ) -> None:
        """
        Обрабатывает сообщение с задачей на бэктест.

        Args:
            message: Kafka сообщение с BacktestRequestMessage.

        Raises:
            FatalError: При невосстановимых ошибках (невалидные данные).
            RetryableError: При временных ошибках (БД недоступна).
        """
        # Устанавливаем correlation_id для трейсинга
        set_correlation_id(message.correlation_id)

        job_id_str = str(message.value.job_id)

        logger.info(
            "backtest_consumer.message_received",
            job_id=job_id_str,
            status=message.value.status,
        )

        try:
            # Проверяем статус сообщения (для "круга почета" от Data Processor)
            skip_indicator_check = False
            if message.value.status:
                # Это ответ от Data Processor после расчета индикаторов
                if message.value.status == "CALCULATION_SUCCESS":
                    logger.info(
                        "backtest_consumer.indicators_ready",
                        job_id=job_id_str,
                    )
                    # Продолжаем обработку бэктеста, пропуская проверку индикаторов
                    skip_indicator_check = True
                elif message.value.status == "CALCULATION_FAILURE":
                    logger.error(
                        "backtest_consumer.indicator_calculation_failed",
                        job_id=job_id_str,
                    )
                    await self.backtest_repo.update_job_status(
                        message.value.job_id,
                        "FAILED",
                        error_message="Indicator calculation failed",
                    )
                    return
                else:
                    logger.warning(
                        "backtest_consumer.unknown_status",
                        job_id=job_id_str,
                        status=message.value.status,
                    )
                    return

            # Получаем клиента из пула
            client = await self.ch_client_pool.acquire()
            try:
                # Обрабатываем бэктест через orchestrator
                await self.orchestrator.process_backtest(
                    job_id=message.value.job_id,
                    client=client,
                    correlation_id=message.correlation_id,
                    skip_indicator_check=skip_indicator_check,
                )

                logger.info(
                    "backtest_consumer.processing_completed",
                    job_id=job_id_str,
                )

            finally:
                # Возвращаем клиента в пул
                await self.ch_client_pool.release(client)

        except ValueError as e:
            # Невосстановимая ошибка - невалидные входные данные
            logger.error(
                "backtest_consumer.validation_error",
                job_id=job_id_str,
                error=str(e),
                error_type="ValueError",
            )
            raise FatalError(f"Invalid data: {e}") from e

        except asyncio.TimeoutError as e:
            # Временная ошибка - timeout бэктеста, можно retry
            logger.warning(
                "backtest_consumer.timeout_error",
                job_id=job_id_str,
                error=str(e),
                timeout_seconds=BACKTEST_TIMEOUT_SECONDS,
            )
            raise RetryableError(
                f"Backtest timeout after {BACKTEST_TIMEOUT_SECONDS}s: {e}"
            ) from e

        except ClickHouseError as e:
            # Временная ошибка - ClickHouse недоступен, можно retry
            logger.warning(
                "backtest_consumer.clickhouse_error",
                job_id=job_id_str,
                error=str(e),
                error_type="ClickHouseError",
            )
            raise RetryableError(f"ClickHouse connection error: {e}") from e

        except BacktestExecutionError as e:
            # Ошибка выполнения бэктеста - анализируем причину
            error_msg = str(e).lower()

            if "timeout" in error_msg:
                # Timeout в симуляции - можно retry
                logger.warning(
                    "backtest_consumer.execution_timeout",
                    job_id=job_id_str,
                    error=str(e),
                )
                raise RetryableError(f"Execution timeout: {e}") from e
            else:
                # Другие ошибки выполнения - fatal
                logger.error(
                    "backtest_consumer.execution_failed",
                    job_id=job_id_str,
                    error=str(e),
                )
                raise FatalError(f"Execution failed: {e}") from e

        except Exception as e:
            # Неожиданная ошибка - логируем как critical с полным traceback
            logger.critical(
                "backtest_consumer.unexpected_error",
                job_id=job_id_str,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise FatalError(
                f"Unexpected error during backtest processing: "
                f"{type(e).__name__}: {e}"
            ) from e
