"""
Strategy Repository для работы со стратегиями.

Отвечает за:
- Получение списка активных RT стратегий
- Получение определений стратегий для real-time торговли
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from tradeforge_db import Strategies
from tradeforge_logger import get_logger

from .base import BaseRepository

logger = get_logger(__name__)


class StrategyRepository(BaseRepository):
    """
    Репозиторий для работы со стратегиями из PostgreSQL.

    Используется для получения стратегий для RT торговли.
    """

    async def get_active_rt_strategies_definitions(
        self,
    ) -> list[dict[str, Any]]:
        """
        Возвращает список определений всех активных RT стратегий.

        Используется RT Processor для загрузки стратегий при запуске.

        Returns:
            Список словарей с id, name и definition стратегий.
            Пустой список при ошибках.

        Note:
            См. TODO.md #3 - добавить фильтр по is_active_for_trading
            когда колонка будет добавлена в схему БД.
        """
        try:
            async with self.db_manager.session() as session:
                stmt = select(
                    Strategies.id, Strategies.name, Strategies.definition
                )
                # Запланировано: фильтр по is_active_for_trading (см. TODO.md #3)
                # .where(Strategies.is_active_for_trading == True)

                result = await session.execute(stmt)
                rows = result.all()

                records = [dict(row._mapping) for row in rows]
                logger.info(
                    "strategy_repo.rt_strategies_loaded",
                    count=len(records),
                )
                return records
        except Exception as e:
            logger.exception(
                "strategy_repo.rt_strategies_load_failed",
                error=str(e),
            )
            return []
