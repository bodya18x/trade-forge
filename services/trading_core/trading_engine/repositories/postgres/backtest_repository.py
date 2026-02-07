"""
Backtest Repository для работы с задачами на бэктест.

Отвечает за операции с BacktestJobs и BacktestResults:
- Получение деталей задачи
- Обновление статуса задачи
- Сохранение результатов бэктеста
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from tradeforge_db import BacktestJobs, BacktestResults, Strategies
from tradeforge_logger import get_logger

from core.common import JobStatus, convert_to_moscow_tz
from models.repository import BacktestJobDetails

from .base import BaseRepository
from .batch_repository import BatchRepository

logger = get_logger(__name__)


class BacktestRepository(BaseRepository):
    """
    Репозиторий для работы с BacktestJobs и BacktestResults.

    Предоставляет методы для:
    - Получения деталей задачи на бэктест (с join к Strategies)
    - Обновления статуса задачи
    - Сохранения результатов выполненного бэктеста
    """

    async def get_job_details(
        self, job_id: uuid.UUID
    ) -> BacktestJobDetails | None:
        """
        Получает полную информацию о задаче на бэктест и связанной стратегии.

        Использует retry логику из BaseRepository.

        Args:
            job_id: UUID задачи на бэктест.

        Returns:
            BacktestJobDetails с деталями задачи и стратегии или None если не найдено.

        Raises:
            SQLAlchemyError: При критических ошибках БД после всех попыток.
        """
        return await self._execute_with_retry(self._do_get_job_details, job_id)

    async def _do_get_job_details(
        self, job_id: uuid.UUID
    ) -> BacktestJobDetails | None:
        """
        Внутренний метод для получения деталей задачи на бэктест.

        Выполняет JOIN с таблицей Strategies для получения определения стратегии.

        Args:
            job_id: UUID задачи на бэктест.

        Returns:
            BacktestJobDetails или None если задача не найдена.
        """
        try:
            async with self.db_manager.session() as session:
                stmt = (
                    select(
                        BacktestJobs.id.label("job_id"),
                        BacktestJobs.user_id,
                        BacktestJobs.ticker,
                        BacktestJobs.timeframe,
                        BacktestJobs.start_date,
                        BacktestJobs.end_date,
                        BacktestJobs.status,
                        BacktestJobs.simulation_params,
                        Strategies.id.label("strategy_id"),
                        Strategies.name.label("strategy_name"),
                        Strategies.definition.label("strategy_definition"),
                    )
                    .join(
                        Strategies, BacktestJobs.strategy_id == Strategies.id
                    )
                    .where(BacktestJobs.id == job_id)
                )

                result = await session.execute(stmt)
                row = result.first()

                if row:
                    logger.debug(
                        "backtest_repo.job_details_found",
                        job_id=str(job_id),
                    )

                    job_data = dict(row._mapping)

                    # Конвертируем даты в московское время если нужно
                    for date_field in ["start_date", "end_date"]:
                        job_data[date_field] = convert_to_moscow_tz(
                            job_data[date_field]
                        )

                    # Создаем и валидируем Pydantic модель
                    return BacktestJobDetails(**job_data)

                logger.warning(
                    "backtest_repo.job_not_found",
                    job_id=str(job_id),
                )
                return None
        except Exception as e:
            logger.exception(
                "backtest_repo.job_details_fetch_failed",
                job_id=str(job_id),
                error=str(e),
            )
            return None

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: JobStatus,
        error_message: str | None = None,
    ) -> None:
        """
        Обновляет статус задачи на бэктест.

        ВАЖНО: Автоматически обновляет счетчики и статус batch если job принадлежит batch.
        Использует BatchRepository для управления жизненным циклом батча.

        Args:
            job_id: UUID задачи на бэктест.
            status: Новый статус задачи (JobStatus enum).
            error_message: Сообщение об ошибке (опционально).

        Raises:
            SQLAlchemyError: При ошибке работы с БД.
        """
        try:
            async with self.db_manager.session() as session:
                # 1. Получаем текущий job
                stmt = select(BacktestJobs).where(BacktestJobs.id == job_id)
                result = await session.execute(stmt)
                job = result.scalar_one_or_none()

                if not job:
                    logger.warning(
                        "backtest_repo.job_not_found_for_update",
                        job_id=str(job_id),
                    )
                    return

                old_status = job.status
                batch_id = job.batch_id

                # 2. Обновляем job
                job.status = status
                job.error_message = error_message
                job.updated_at = datetime.now(timezone.utc)

                # 3. Если job принадлежит batch - обновляем batch counters
                if batch_id:
                    batch_repo = BatchRepository()
                    await batch_repo.update_batch_counters(
                        session=session,
                        batch_id=batch_id,
                        old_job_status=old_status,
                        new_job_status=status,
                    )
                    logger.debug(
                        "backtest_repo.batch_counters_updated",
                        job_id=str(job_id),
                        batch_id=str(batch_id),
                        old_status=old_status,
                        new_status=status,
                    )

                logger.info(
                    "backtest_repo.job_status_updated",
                    job_id=str(job_id),
                    old_status=old_status,
                    new_status=status,
                    has_batch=batch_id is not None,
                )

        except Exception as e:
            logger.exception(
                "backtest_repo.job_status_update_failed",
                job_id=str(job_id),
                status=status,
                error=str(e),
            )
            raise

    async def save_backtest_result(
        self,
        job_id: uuid.UUID,
        metrics: dict[str, Any],
        trades: list[dict[str, Any]],
    ) -> uuid.UUID | None:
        """
        Сохраняет результат выполненного бэктеста в базу данных.

        Args:
            job_id: UUID задачи на бэктест.
            metrics: Словарь с метриками бэктеста (ROI, Win Rate, Max Drawdown, etc.).
            trades: Список сделок в виде словарей.

        Returns:
            UUID созданной записи результата или None при ошибке.

        Raises:
            SQLAlchemyError: При ошибке работы с БД.
        """
        result_id = uuid.uuid4()

        try:
            async with self.db_manager.session() as session:
                backtest_result = BacktestResults(
                    id=result_id,
                    job_id=job_id,
                    metrics=metrics,
                    trades=trades,
                )

                session.add(backtest_result)

                logger.info(
                    "backtest_repo.result_saved",
                    job_id=str(job_id),
                    result_id=str(result_id),
                    trades_count=len(trades),
                    metrics_keys=list(metrics.keys())[:10],  # Первые 10 ключей
                )
                return result_id
        except Exception as e:
            logger.exception(
                "backtest_repo.result_save_failed",
                job_id=str(job_id),
                error=str(e),
            )
            return None
