"""
Batch Repository для работы с пакетами бэктестов.

Отвечает за:
- Обновление счетчиков batch
- Обновление статуса batch
- Управление жизненным циклом batch
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import BacktestBatches
from tradeforge_logger import get_logger

from .base import BaseRepository

logger = get_logger(__name__)


class BatchRepository(BaseRepository):
    """
    Репозиторий для работы с пакетами бэктестов (BacktestBatches).

    Batch - это группа связанных задач на бэктест,
    например, при запуске оптимизации параметров стратегии.

    Управляет счетчиками completed/failed и статусом batch.
    """

    async def update_batch_counters(
        self,
        session: AsyncSession,
        batch_id: uuid.UUID,
        old_job_status: str,
        new_job_status: str,
    ) -> None:
        """
        Обновляет счетчики batch в существующей транзакции с атомарным SQL обновлением.

        ВАЖНО: Использует атомарное обновление на уровне SQL для предотвращения race condition.
        Этот метод должен вызываться внутри активной транзакции.

        Args:
            session: Активная SQLAlchemy сессия (из внешней транзакции).
            batch_id: UUID пакета бэктестов.
            old_job_status: Предыдущий статус задачи.
            new_job_status: Новый статус задачи.

        Raises:
            SQLAlchemyError: При ошибке работы с БД.
        """
        try:
            # Вычисляем изменения счетчиков
            completed_delta = 0
            failed_delta = 0

            # Логика подсчета дельт
            if new_job_status == "COMPLETED" and old_job_status != "COMPLETED":
                completed_delta = 1
            elif (
                new_job_status != "COMPLETED" and old_job_status == "COMPLETED"
            ):
                completed_delta = -1

            if new_job_status == "FAILED" and old_job_status != "FAILED":
                failed_delta = 1
            elif new_job_status != "FAILED" and old_job_status == "FAILED":
                failed_delta = -1

            # Если нет изменений - выходим
            if completed_delta == 0 and failed_delta == 0:
                logger.debug(
                    "batch_repo.no_counter_changes",
                    batch_id=str(batch_id),
                    old_status=old_job_status,
                    new_status=new_job_status,
                )
                return

            # ✅ АТОМАРНОЕ обновление счетчиков на уровне SQL
            # Это предотвращает race condition при параллельной обработке
            stmt = (
                update(BacktestBatches)
                .where(BacktestBatches.id == batch_id)
                .values(
                    completed_count=BacktestBatches.completed_count
                    + completed_delta,
                    failed_count=BacktestBatches.failed_count + failed_delta,
                    updated_at=datetime.now(timezone.utc),
                )
                .returning(
                    BacktestBatches.completed_count,
                    BacktestBatches.failed_count,
                    BacktestBatches.total_count,
                    BacktestBatches.status,
                )
            )

            result = await session.execute(stmt)
            row = result.first()

            if not row:
                logger.warning(
                    "batch_repo.batch_not_found",
                    batch_id=str(batch_id),
                )
                return

            completed_count, failed_count, total_count, current_status = row

            # Вычисляем новый статус batch
            finished_count = completed_count + failed_count
            new_status = None

            if finished_count == total_count:
                # Все задачи завершены
                if failed_count == 0:
                    new_status = "COMPLETED"
                elif completed_count == 0:
                    new_status = "FAILED"
                else:
                    new_status = "PARTIALLY_FAILED"
            elif finished_count > 0 and current_status == "PENDING":
                # Есть завершенные задачи, но не все
                new_status = "RUNNING"

            # Обновляем статус если нужно
            if new_status and new_status != current_status:
                update_status_stmt = (
                    update(BacktestBatches)
                    .where(BacktestBatches.id == batch_id)
                    .values(
                        status=new_status,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.execute(update_status_stmt)

                logger.info(
                    "batch_repo.status_updated",
                    batch_id=str(batch_id),
                    old_status=current_status,
                    new_status=new_status,
                    completed=completed_count,
                    failed=failed_count,
                    total=total_count,
                )

            logger.debug(
                "batch_repo.counters_updated_atomic",
                batch_id=str(batch_id),
                completed_count=completed_count,
                failed_count=failed_count,
                total_count=total_count,
                status=new_status or current_status,
                completed_delta=completed_delta,
                failed_delta=failed_delta,
            )

        except Exception as e:
            logger.exception(
                "batch_repo.counters_update_failed",
                batch_id=str(batch_id),
                error=str(e),
            )
            raise
