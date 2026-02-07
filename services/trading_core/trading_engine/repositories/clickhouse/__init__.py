"""
ClickHouse Repository Module.

Объединяет компоненты для работы с ClickHouse:
- ClickHouseClientPool: Управление пулом асинхронных клиентов
- ClickHouseRepository: Репозиторий для загрузки данных бэктестов

Централизованное расположение всей логики ClickHouse для лучшей организации кода.
"""

from __future__ import annotations

from .pool import ClickHouseClientPool
from .repository import ClickHouseRepository

__all__ = [
    "ClickHouseClientPool",
    "ClickHouseRepository",
]
