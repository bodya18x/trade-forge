"""
ClickHouse Client Pool Manager.

Управляет пулом асинхронных клиентов ClickHouse для обработки запросов.
Обеспечивает graceful shutdown с ожиданием завершения всех активных задач.
"""

from __future__ import annotations

import asyncio
import time

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient
from tradeforge_logger import get_logger

logger = get_logger(__name__)


class ClickHouseClientPool:
    """
    Пул асинхронных клиентов ClickHouse с graceful shutdown.

    Управляет жизненным циклом пула клиентов:
    - Создание фиксированного количества клиентов
    - Thread-safe получение/возврат клиентов через asyncio.Queue
    - Graceful shutdown с ожиданием завершения активных задач

    Attributes:
        pool: Очередь доступных клиентов.
        clients: Список всех созданных клиентов.
        size: Размер пула.

    Example:
        >>> pool = ClickHouseClientPool(
        ...     size=5,
        ...     host="localhost",
        ...     port=8123,
        ...     username="default",
        ...     password="",
        ...     database="trader"
        ... )
        >>> await pool.initialize()
        >>> try:
        ...     client = await pool.acquire()
        ...     # работа с клиентом
        ... finally:
        ...     await pool.release(client)
        ...     await pool.close()
    """

    def __init__(
        self,
        size: int,
        host: str,
        port: int,
        username: str,
        password: str,
        database: str,
        settings: dict[str, str] | None = None,
    ):
        """
        Инициализирует пул клиентов.

        Args:
            size: Количество клиентов в пуле.
            host: ClickHouse host.
            port: ClickHouse HTTP port.
            username: Имя пользователя.
            password: Пароль.
            database: База данных.
            settings: Дополнительные настройки ClickHouse.
        """
        self.size = size
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.settings = settings or {}

        self.pool: asyncio.Queue[AsyncClient] = asyncio.Queue(maxsize=size)
        self.clients: list[AsyncClient] = []

        logger.info(
            "clickhouse_pool.created",
            size=size,
            host=host,
            database=database,
        )

    async def initialize(self) -> None:
        """
        Создает клиентов и заполняет пул.

        Raises:
            Exception: При ошибке создания клиентов.
        """
        logger.info(
            "clickhouse_pool.initializing",
            size=self.size,
        )

        try:
            for idx in range(self.size):
                client = await clickhouse_connect.get_async_client(
                    host=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    database=self.database,
                    settings=self.settings,
                )
                self.clients.append(client)
                await self.pool.put(client)

                logger.debug(
                    "clickhouse_pool.client_created",
                    client_index=idx,
                )

            logger.info(
                "clickhouse_pool.initialized",
                pool_size=self.size,
            )

        except Exception as e:
            logger.exception(
                "clickhouse_pool.initialization_failed",
                error=str(e),
            )
            # Cleanup частично созданных клиентов
            self._cleanup_clients()
            raise

    async def acquire(self) -> AsyncClient:
        """
        Получает клиента из пула.

        Блокируется если пул пуст, пока клиент не станет доступен.

        Returns:
            Асинхронный клиент ClickHouse.
        """
        client = await self.pool.get()
        logger.debug(
            "clickhouse_pool.client_acquired",
            pool_remaining=self.pool.qsize(),
        )
        return client

    async def release(self, client: AsyncClient) -> None:
        """
        Возвращает клиента обратно в пул.

        Args:
            client: Клиент для возврата.
        """
        await self.pool.put(client)
        logger.debug(
            "clickhouse_pool.client_released",
            pool_available=self.pool.qsize(),
        )

    async def close(self, timeout: int = 30) -> None:
        """
        Выполняет graceful shutdown пула.

        Ждет возврата всех клиентов в пул (завершения активных задач),
        затем закрывает все соединения.

        Args:
            timeout: Максимальное время ожидания завершения задач (секунды).
        """
        logger.info(
            "clickhouse_pool.shutdown_starting",
            expected_clients=len(self.clients),
            clients_in_pool=self.pool.qsize(),
        )

        # Ждем возврата всех клиентов в пул
        wait_start = time.time()
        while self.pool.qsize() < len(self.clients):
            elapsed = time.time() - wait_start
            if elapsed > timeout:
                logger.warning(
                    "clickhouse_pool.shutdown_timeout",
                    clients_in_pool=self.pool.qsize(),
                    expected=len(self.clients),
                    elapsed_seconds=round(elapsed, 2),
                )
                break
            await asyncio.sleep(0.1)

        logger.info(
            "clickhouse_pool.all_clients_returned",
            clients_in_pool=self.pool.qsize(),
            expected=len(self.clients),
        )

        # Закрываем все клиенты
        self._cleanup_clients()

        logger.info("clickhouse_pool.shutdown_complete")

    def _cleanup_clients(self) -> None:
        """Закрывает все созданные клиенты."""
        logger.info(
            "clickhouse_pool.closing_clients",
            total_clients=len(self.clients),
        )

        for idx, client in enumerate(self.clients):
            try:
                client.close()
                logger.debug(
                    "clickhouse_pool.client_closed",
                    client_index=idx,
                )
            except Exception as e:
                logger.warning(
                    "clickhouse_pool.client_close_error",
                    client_index=idx,
                    error=str(e),
                )

        self.clients.clear()
        logger.info("clickhouse_pool.all_clients_closed")
