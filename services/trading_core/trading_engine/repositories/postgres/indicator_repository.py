"""
Indicator Repository для работы с реестром индикаторов.

Отвечает за:
- Получение полного реестра доступных индикаторов
- Получение метаданных индикаторов (имена, параметры)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from tradeforge_db import UsersIndicators
from tradeforge_logger import get_logger

from .base import BaseRepository

logger = get_logger(__name__)


class IndicatorRepository(BaseRepository):
    """
    Репозиторий для работы с реестром индикаторов.

    Используется для получения списка доступных индикаторов
    и их метаданных для построения стратегий.
    """

    async def get_full_indicator_registry(
        self,
    ) -> dict[str, dict[str, Any]]:
        """
        Извлекает полный реестр всех индикаторов из справочника.

        Возвращает словарь где ключ - это indicator_key (уникальный идентификатор),
        а значение - словарь с метаданными индикатора.

        Returns:
            Словарь {indicator_key: {"name": ..., "params": ..., "is_hot": ...}}.
            Пустой словарь при ошибках.

        Example:
            ```python
            registry = await repo.get_full_indicator_registry()
            # {
            #   "ema_timeperiod_12_value": {
            #       "name": "EMA",
            #       "params": {"timeperiod": 12},
            #       "is_hot": True
            #   },
            #   ...
            # }
            ```
        """
        try:
            async with self.db_manager.session() as session:
                stmt = select(
                    UsersIndicators.indicator_key,
                    UsersIndicators.name,
                    UsersIndicators.params,
                    UsersIndicators.is_hot,
                )

                result = await session.execute(stmt)
                rows = result.all()

                registry = {}
                for row in rows:
                    registry[row.indicator_key] = {
                        "name": row.name,
                        "params": row.params,
                        "is_hot": row.is_hot,
                    }

                logger.info(
                    "indicator_repo.registry_loaded",
                    indicators_count=len(registry),
                )
                return registry
        except Exception as e:
            logger.exception(
                "indicator_repo.registry_load_failed",
                error=str(e),
            )
            raise RuntimeError(
                f"Failed to load indicator registry: {e}. "
                "Trading engine cannot operate without indicator registry."
            ) from e
