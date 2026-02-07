"""
Ticker Repository для работы с информацией о тикерах.

Отвечает за:
- Кэширование информации о тикерах
- Автоматическое обновление кэша по TTL
- Получение информации о конкретном тикере
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from tradeforge_db import Tickers
from tradeforge_logger import get_logger

from core import DataNotFoundError
from models.repository import TickerInfo

from .base import BaseRepository

logger = get_logger(__name__)


class TickerRepository(BaseRepository):
    """
    Репозиторий для работы с тикерами из PostgreSQL.

    Использует in-memory кэш с автоматическим обновлением по TTL.

    Attributes:
        _ticker_cache: In-memory кэш тикеров {symbol -> TickerInfo}.
        _cache_initialized: Флаг инициализации кэша.
        _cache_timestamp: Время последнего обновления кэша.
        _cache_ttl: Time-To-Live для кэша (по умолчанию 1 час).
    """

    def __init__(self, cache_ttl_hours: int = 1):
        """
        Инициализирует репозиторий с настраиваемым TTL кэша.

        Args:
            cache_ttl_hours: Количество часов до автоматического обновления кэша.
        """
        super().__init__()
        self._ticker_cache: dict[str, dict] = {}
        self._cache_initialized = False
        self._cache_timestamp: datetime | None = None
        self._cache_ttl = timedelta(hours=cache_ttl_hours)

        logger.info(
            "ticker_repo.initialized",
            cache_ttl_hours=cache_ttl_hours,
        )

    async def get_ticker_info(self, ticker_symbol: str) -> TickerInfo | None:
        """
        Возвращает информацию о тикере с автоматическим обновлением кэша.

        Если кэш устарел (превышен TTL), автоматически обновляет его.

        Args:
            ticker_symbol: Символ тикера (например, "SBER").

        Returns:
            TickerInfo с информацией о тикере или None, если тикер не найден.

        Raises:
            DataNotFoundError: Если lot_size отсутствует или некорректен.
        """
        # Проверяем и обновляем кэш при необходимости
        await self._refresh_cache_if_needed()

        ticker_data = self._ticker_cache.get(ticker_symbol)

        if ticker_data is None:
            logger.error(
                "ticker_repo.ticker_not_found",
                ticker=ticker_symbol,
                message="Critical: Ticker not found in database",
            )
            return None

        # Проверка корректности lot_size
        lot_size = ticker_data.get("lot_size")
        if lot_size is None or lot_size <= 0:
            raise DataNotFoundError(
                f"Ticker '{ticker_symbol}' has invalid lot_size: {lot_size}. "
                "Backtest impossible without lot size."
            )

        # Создаем и валидируем Pydantic модель
        return TickerInfo(**ticker_data)

    async def _refresh_cache_if_needed(self) -> None:
        """
        Проверяет TTL кэша и обновляет его при необходимости.

        Обновление происходит если:
        1. Кэш не инициализирован
        2. Timestamp отсутствует
        3. Превышен TTL (время с последнего обновления > cache_ttl)
        """
        # Кэш не инициализирован - обновляем
        if not self._cache_initialized:
            logger.info("ticker_repo.cache_not_initialized_refreshing")
            await self._refresh_ticker_cache()
            return

        # Timestamp отсутствует - обновляем
        if self._cache_timestamp is None:
            logger.warning(
                "ticker_repo.cache_timestamp_missing_refreshing",
            )
            await self._refresh_ticker_cache()
            return

        # Проверяем TTL
        elapsed = datetime.now() - self._cache_timestamp
        if elapsed > self._cache_ttl:
            logger.info(
                "ticker_repo.cache_expired_refreshing",
                elapsed_seconds=elapsed.total_seconds(),
                ttl_seconds=self._cache_ttl.total_seconds(),
            )
            await self._refresh_ticker_cache()

    async def _refresh_ticker_cache(self) -> None:
        """
        Обновляет внутренний кэш информации о тикерах из PostgreSQL.

        Использует retry логику из BaseRepository.

        Raises:
            SQLAlchemyError: При критических ошибках БД после всех попыток.
        """
        logger.info("ticker_repo.cache_refreshing")

        await self._execute_with_retry(self._do_refresh_ticker_cache)

    async def _do_refresh_ticker_cache(self) -> None:
        """
        Внутренний метод для обновления кэша тикеров.

        Загружает все активные тикеры из БД и обновляет кэш.
        Устанавливает timestamp для TTL контроля.
        """
        try:
            async with self.db_manager.session() as session:
                stmt = select(
                    Tickers.symbol,
                    Tickers.lot_size,
                    Tickers.min_step,
                    Tickers.decimals,
                    Tickers.currency,
                ).where(
                    Tickers.is_active == True  # noqa: E712
                )

                result = await session.execute(stmt)
                rows = result.all()

                # Очищаем старый кэш
                self._ticker_cache.clear()

                # Заполняем новыми данными
                for row in rows:
                    self._ticker_cache[row.symbol] = {
                        "lot_size": row.lot_size,
                        "min_step": row.min_step,
                        "decimals": row.decimals,
                        "currency": row.currency,
                    }

                # Обновляем метаданные кэша
                self._cache_initialized = True
                self._cache_timestamp = datetime.now()

                logger.info(
                    "ticker_repo.cache_refreshed",
                    tickers_count=len(self._ticker_cache),
                    timestamp=self._cache_timestamp.isoformat(),
                )
        except Exception as e:
            logger.exception(
                "ticker_repo.cache_refresh_failed",
                error=str(e),
            )
            raise

    async def force_refresh_cache(self) -> None:
        """
        Принудительно обновляет кэш тикеров, игнорируя TTL.

        Полезно для тестирования или когда нужно сразу получить свежие данные.
        """
        logger.info("ticker_repo.force_refresh_requested")
        await self._refresh_ticker_cache()
