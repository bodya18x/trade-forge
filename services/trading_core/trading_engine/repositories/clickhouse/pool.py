"""
ClickHouse Client Pool Manager.

Управляет пулом асинхронных клиентов ClickHouse для batch-обработки бэктестов.
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
        settings: dict | None = None,
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

    async def _ping_client(self, client: AsyncClient) -> bool:
        """
        Проверяет здоровье клиента через простой запрос.

        Args:
            client: Клиент для проверки.

        Returns:
            True если клиент здоров, False если соединение потеряно.
        """
        try:
            await client.query("SELECT 1")
            return True
        except Exception as e:
            logger.debug(
                "clickhouse_pool.ping_failed",
                error=str(e),
            )
            return False

    async def _recreate_client(self, old_client: AsyncClient) -> AsyncClient:
        """
        Пересоздает клиента при потере соединения.

        Args:
            old_client: Старый клиент для закрытия.

        Returns:
            Новый здоровый клиент.

        Raises:
            Exception: При невозможности создать новое соединение.
        """
        # Пытаемся закрыть старый клиент (best effort)
        try:
            await old_client.close()
        except Exception as e:
            logger.debug(
                "clickhouse_pool.old_client_close_error",
                error=str(e),
            )

        # Создаем новый клиент
        new_client = await clickhouse_connect.get_async_client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            database=self.database,
            settings=self.settings,
        )

        logger.info(
            "clickhouse_pool.client_recreated",
            host=self.host,
            database=self.database,
        )

        return new_client

    async def acquire(self) -> AsyncClient:
        """
        Получает клиента из пула с проверкой здоровья соединения.

        Если клиент потерял соединение, автоматически пересоздает его.
        Блокируется если пул пуст, пока клиент не станет доступен.

        Returns:
            Асинхронный клиент ClickHouse с активным соединением.

        Raises:
            Exception: При невозможности получить здоровый клиент.
        """
        client = await self.pool.get()
        logger.debug(
            "clickhouse_pool.client_acquired",
            pool_remaining=self.pool.qsize(),
        )

        # Проверяем здоровье клиента
        is_healthy = await self._ping_client(client)

        if not is_healthy:
            logger.warning(
                "clickhouse_pool.unhealthy_client_detected",
                host=self.host,
                database=self.database,
            )

            try:
                client = await self._recreate_client(client)
                logger.info(
                    "clickhouse_pool.client_health_restored",
                    host=self.host,
                    database=self.database,
                )
            except Exception as e:
                logger.error(
                    "clickhouse_pool.client_recreation_failed",
                    host=self.host,
                    database=self.database,
                    error=str(e),
                )
                # Возвращаем клиента обратно в пул (он мертвый, но пусть будет в пуле)
                await self.pool.put(client)
                raise

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
