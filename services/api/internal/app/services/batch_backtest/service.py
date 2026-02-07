"""
Сервис для работы с групповыми бэктестами.

Координирует создание и управление группами бэктестов.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import BacktestJobs
from tradeforge_logger import get_logger
from tradeforge_schemas import BacktestCreateRequest

from app.crud import crud_backtests, crud_batch_backtests, crud_strategies
from app.services.backtest import BacktestService
from app.types import BatchID, UserID

from .response_builder import BatchResponseBuilder
from .validator import BatchValidator

log = get_logger(__name__)


class BatchBacktestService:
    """
    Сервис для управления групповыми бэктестами.

    Отвечает за создание группы бэктестов, управление их статусами
    и предоставление агрегированной информации.
    """

    def __init__(self, db: AsyncSession, redis: Redis, user_id: UserID):
        """
        Инициализирует сервис групповых бэктестов.

        Args:
            db: Асинхронная сессия базы данных
            redis: Клиент Redis
            user_id: UUID пользователя
        """
        self.db = db
        self.redis = redis
        self.user_id = user_id
        self.backtest_service = BacktestService(db, redis, user_id)
        self.validator = BatchValidator(db, user_id, self.backtest_service)
        self.response_builder = BatchResponseBuilder(db, user_id)

    async def submit_batch_backtest(
        self,
        description: str,
        backtests: list[
            dict[str, Any]
        ],  # Any: сырой JSON запрос от API с переменными структурами
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Создает групповой бэктест и запускает все индивидуальные задачи.

        Использует атомарный подход: либо все задачи валидны и создаются,
        либо при первой ошибке весь batch отклоняется с HTTP 422.

        Args:
            description: Описание группы
            backtests: Список параметров для каждого бэктеста (raw JSON)
            idempotency_key: Ключ идемпотентности (не используется для batch)

        Returns:
            dict[str, Any] - JSON-сериализуемый словарь с данными созданного batch

        Raises:
            HTTPException: При ошибках валидации любой задачи (HTTP 422)
        """
        try:
            # ШАГ 1: ПРЕДВАРИТЕЛЬНАЯ ВАЛИДАЦИЯ ВСЕХ ЗАДАЧ
            await self.validator.validate_all_backtests(backtests)

            # ШАГ 2: ПРОВЕРЯЕМ ДОСТАТОЧНОСТЬ ДАННЫХ В CLICKHOUSE
            data_sufficiency_results = (
                await self.validator.check_data_sufficiency_for_all(backtests)
            )

            # ШАГ 3: ВСЕ ЗАДАЧИ ВАЛИДНЫ → СОЗДАЕМ BATCH И ЗАДАЧИ
            log.info(
                "batch.backtest.creation.started",
                user_id=str(self.user_id),
                total_count=len(backtests),
            )

            # Оценка времени выполнения
            estimated_time = self.response_builder.estimate_completion_time(
                len(backtests)
            )

            # Создаем запись группового бэктеста
            batch_data = await crud_batch_backtests.create_batch_backtest(
                self.db,
                user_id=self.user_id,
                description=description,
                total_count=len(backtests),
                estimated_completion_time=estimated_time,
            )

            batch_id = batch_data.id
            individual_jobs = []

            # Создаем все задачи с учетом достаточности данных
            for backtest_params in backtests:
                backtest_request = BacktestCreateRequest(**backtest_params)

                # Получаем результат проверки достаточности данных
                data_key = (
                    backtest_request.ticker,
                    backtest_request.timeframe,
                    backtest_request.start_date,
                    backtest_request.end_date,
                )

                sufficiency_result = data_sufficiency_results.get(
                    data_key, {"has_sufficient_data": True}
                )
                has_sufficient_data = sufficiency_result.get(
                    "has_sufficient_data", True
                )

                if has_sufficient_data:
                    # Данных достаточно → создаем нормальную задачу
                    job = await self.backtest_service.submit_backtest(
                        backtest_in=backtest_request,
                        idempotency_key=None,
                        batch_id=batch_id,
                        skip_validation=True,
                    )
                else:
                    # Данных недостаточно → создаем FAILED задачу без отправки в Kafka
                    error_message = sufficiency_result.get(
                        "error_message",
                        "Недостаточно данных для выполнения бэктеста",
                    )

                    job = await self._create_failed_job_for_insufficient_data(
                        backtest_request, batch_id, error_message
                    )

                    # Обновляем счетчик failed в batch сразу
                    await crud_batch_backtests.update_batch_counters(
                        self.db,
                        batch_id=batch_id,
                        failed_delta=1,
                    )

                individual_jobs.append(
                    {
                        "job_id": job.id,
                        "status": job.status.value,
                        "ticker": job.ticker,
                        "timeframe": job.timeframe,
                        "completion_time": None,
                        "error_message": job.error_message,
                    }
                )

            # Формируем ответ
            batch_response = await self.response_builder.build_batch_response(
                batch_id, individual_jobs
            )

            log.info(
                "batch.backtest.created",
                batch_id=str(batch_id),
                user_id=str(self.user_id),
                total_count=len(backtests),
            )

            return batch_response

        except HTTPException:
            # HTTPException пробрасываем как есть
            raise
        except Exception as e:
            await self.db.rollback()
            log.error(
                "batch.backtest.creation.failed",
                user_id=str(self.user_id),
                description=description,
                total_count=len(backtests),
                error=str(e),
                exc_info=True,
            )
            raise

    async def get_batch_status(
        self, batch_id: BatchID
    ) -> (
        dict[str, Any] | None
    ):  # Any: JSON-сериализуемый словарь с данными batch
        """
        Получает текущий статус группового бэктеста.

        Args:
            batch_id: ID группового бэктеста

        Returns:
            dict[str, Any] - JSON-сериализуемый словарь с данными batch или None если не найден
        """
        try:
            # Получаем основные данные batch
            batch_data = await crud_batch_backtests.get_batch_by_id(
                self.db, batch_id=batch_id, user_id=self.user_id
            )

            if not batch_data:
                return None

            # Получаем актуальные данные индивидуальных задач
            individual_jobs = (
                await crud_batch_backtests.get_batch_individual_jobs(
                    self.db, batch_id=batch_id
                )
            )

            return await self.response_builder.build_batch_response(
                batch_id, individual_jobs, batch_data
            )

        except Exception as e:
            log.error(
                "batch.backtest.get_status.failed",
                batch_id=str(batch_id),
                user_id=str(self.user_id),
                error=str(e),
                exc_info=True,
            )
            raise

    async def get_user_batch_backtests(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: str | None = None,
        sort_by: str = "created_at",
        sort_direction: str = "desc",
    ) -> dict[
        str, Any
    ]:  # Any: JSON-сериализуемый словарь с пагинированными batch данными
        """
        Получает список групповых бэктестов пользователя.

        Args:
            limit: Количество записей
            offset: Смещение
            status_filter: Фильтр по статусу
            sort_by: Поле сортировки
            sort_direction: Направление сортировки

        Returns:
            dict[str, Any] - JSON-сериализуемый словарь с пагинированным списком batch:
                           {total, limit, offset, items}
        """
        try:
            # Получаем общее количество
            total = await crud_batch_backtests.get_user_batch_backtests_count(
                self.db,
                user_id=self.user_id,
                status_filter=status_filter,
            )

            # Получаем список batches
            batches = await crud_batch_backtests.get_user_batch_backtests(
                self.db,
                user_id=self.user_id,
                limit=limit,
                offset=offset,
                status_filter=status_filter,
                sort_by=sort_by,
                sort_direction=sort_direction,
            )

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": batches,
            }

        except Exception as e:
            log.error(
                "batch.backtest.list.failed",
                user_id=str(self.user_id),
                error=str(e),
                exc_info=True,
            )
            raise

    async def _create_failed_job_for_insufficient_data(
        self,
        backtest_request: BacktestCreateRequest,
        batch_id: BatchID,
        error_message: str,
    ) -> BacktestJobs:
        """
        Создает задачу со статусом FAILED для бэктеста с недостаточными данными.

        Такая задача НЕ учитывается в лимитах пользователя.

        Args:
            backtest_request: Параметры бэктеста
            batch_id: ID batch
            error_message: Сообщение об ошибке (уже сформированное)

        Returns:
            Созданная задача со статусом FAILED
        """
        # Валидируем даты (нужны parsed даты для создания job)
        parsed_start, parsed_end = (
            self.backtest_service.validator.validate_date_range(
                backtest_request.start_date, backtest_request.end_date
            )
        )

        # Загружаем стратегию для снапшота
        strategy = await crud_strategies.get_strategy_by_id(
            self.db,
            user_id=self.user_id,
            strategy_id=backtest_request.strategy_id,
        )

        # Создаем FAILED задачу
        job = await crud_backtests.create_failed_backtest_job(
            db=self.db,
            user_id=self.user_id,
            backtest_in=backtest_request,
            strategy_snapshot=strategy.definition,
            parsed_start_date=parsed_start,
            parsed_end_date=parsed_end,
            error_message=error_message,
            batch_id=batch_id,
        )

        return job
