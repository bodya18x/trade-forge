"""
Репозиторий для работы с PostgreSQL.

Асинхронные операции с тикерами, рынками и конфигурацией сборов.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db.models import Markets, Tickers
from tradeforge_logger import get_logger

logger = get_logger(__name__)


class PostgresRepository:
    """
    Репозиторий для работы с PostgreSQL.

    Предоставляет методы для работы с тикерами, рынками
    и конфигурацией сборов данных.
    """

    def __init__(self, session: AsyncSession):
        """
        Инициализация репозитория.

        Args:
            session: Асинхронная SQLAlchemy сессия
        """
        self.session = session

    async def get_market_id(self, market_code: str) -> int | None:
        """
        Получает ID рынка по коду.

        Args:
            market_code: Код рынка (например, "moex_stock")

        Returns:
            ID рынка или None если не найден
        """
        stmt = select(Markets.id).where(Markets.market_code == market_code)
        result = await self.session.execute(stmt)
        market_id = result.scalar_one_or_none()

        if market_id is None:
            logger.warning(
                "postgres.market_not_found",
                market_code=market_code,
            )

        return market_id

    async def upsert_tickers(self, tickers_data: list[dict]) -> None:
        """
        Массовая операция UPSERT для тикеров.

        Args:
            tickers_data: Список словарей с данными тикеров

        Raises:
            Exception: При ошибке операции
        """
        if not tickers_data:
            logger.debug("postgres.no_tickers_to_upsert")
            return

        try:
            stmt = insert(Tickers).values(tickers_data)

            # Автоматически получаем все столбцы для обновления,
            # исключая constraint columns и системные поля
            exclude_columns = {"symbol", "market_id", "id", "created_at"}
            update_columns = {
                col.name: getattr(stmt.excluded, col.name)
                for col in Tickers.__table__.columns
                if col.name not in exclude_columns
            }

            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "market_id"],
                set_=update_columns,
            )

            await self.session.execute(stmt)
            await self.session.commit()

            logger.info(
                "postgres.tickers_upserted",
                count=len(tickers_data),
            )

        except Exception as e:
            await self.session.rollback()
            logger.error(
                "postgres.upsert_tickers_failed",
                count=len(tickers_data),
                error=str(e),
                exc_info=True,
            )
            raise

    async def get_active_tickers(
        self, market_code: str = "moex_stock"
    ) -> list[str]:
        """
        Получает список активных тикеров для указанного рынка.

        Args:
            market_code: Код рынка (по умолчанию "moex_stock")

        Returns:
            Список символов активных тикеров
        """
        # Get market_id
        market_id = await self.get_market_id(market_code)
        if not market_id:
            logger.warning(
                "postgres.market_not_found_no_tickers",
                market_code=market_code,
            )
            return []

        stmt = select(Tickers.symbol).where(
            Tickers.is_active == True,
            Tickers.market_id == market_id,
        )
        result = await self.session.execute(stmt)
        tickers = [row[0] for row in result.all()]

        logger.debug(
            "postgres.active_tickers_loaded",
            market_code=market_code,
            count=len(tickers),
        )

        return tickers
