"""
Построение ответов для групповых бэктестов.

Содержит методы для формирования структурированных ответов.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import BacktestBatches
from tradeforge_schemas import BatchBacktestJobInfo

from app.crud import crud_batch_backtests


class BatchResponseBuilder:
    """
    Строитель ответов для групповых бэктестов.

    Формирует структурированные ответы с прогрессом и статусом.
    """

    def __init__(self, db: AsyncSession, user_id: uuid.UUID):
        """
        Инициализирует строитель ответов.

        Args:
            db: Асинхронная сессия базы данных
            user_id: UUID пользователя
        """
        self.db = db
        self.user_id = user_id

    def estimate_completion_time(self, batch_size: int) -> datetime:
        """
        Оценивает время завершения группового бэктеста.

        Использует простую эвристику: 2 минуты на задачу + 1 минута базовое время.

        Args:
            batch_size: Количество задач в группе

        Returns:
            Оценка времени завершения в московском времени
        """
        # Базовая оценка: 2 минуты на задачу + 1 минута базовое время
        estimated_minutes = batch_size * 2 + 1

        # Московский часовой пояс (UTC+3)
        moscow_tz = timezone(timedelta(hours=3))

        # Получаем текущее время в московском часовом поясе
        moscow_now = datetime.now(moscow_tz)

        # Добавляем оценочное время завершения
        estimated_completion = moscow_now + timedelta(
            minutes=estimated_minutes
        )

        return estimated_completion

    async def build_batch_response(
        self,
        batch_id: uuid.UUID,
        individual_jobs: list[
            BatchBacktestJobInfo | dict[str, str | int | float | None]
        ],
        batch_data: BacktestBatches | None = None,
    ) -> dict[str, Any]:
        """
        Строит полный ответ по групповому бэктесту.

        Args:
            batch_id: ID группового бэктеста
            individual_jobs: Список индивидуальных задач (Pydantic модели или словари с примитивными типами)
            batch_data: Данные batch (получает из БД если не переданы)

        Returns:
            dict[str, Any] - JSON-сериализуемый словарь с данными batch и задачами

        Raises:
            ValueError: Если batch не найден
        """
        if not batch_data:
            batch_data = await crud_batch_backtests.get_batch_by_id(
                self.db, batch_id=batch_id, user_id=self.user_id
            )

        if not batch_data:
            raise ValueError(f"Batch {batch_id} not found")

        # Рассчитываем progress_percentage (ограничиваем до 100%)
        total_count = batch_data.total_count
        completed_and_failed = (
            batch_data.completed_count + batch_data.failed_count
        )
        progress_percentage = (
            min((completed_and_failed / total_count * 100), 100.0)
            if total_count > 0
            else 0
        )

        return {
            "batch_id": batch_data.id,
            "status": batch_data.status,
            "description": batch_data.description,
            "total_count": batch_data.total_count,
            "completed_count": batch_data.completed_count,
            "failed_count": batch_data.failed_count,
            "progress_percentage": round(progress_percentage, 1),
            "individual_jobs": individual_jobs,
            "estimated_completion_time": batch_data.estimated_completion_time,
            "created_at": batch_data.created_at,
            "updated_at": batch_data.updated_at,
        }
