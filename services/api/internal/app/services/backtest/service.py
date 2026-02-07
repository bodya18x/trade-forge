"""
Сервис для работы с бэктестами.

Координирует валидацию, идемпотентность и создание задач бэктестинга.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import BacktestJobs, JobStatus
from tradeforge_logger import get_logger
from tradeforge_schemas import BacktestCreateRequest

from app.crud import crud_backtests, crud_strategies
from app.services.kafka_service import kafka_service
from app.types import BatchID, UserID

from .idempotency import IdempotencyManager
from .validators import BacktestValidator

log = get_logger(__name__)


class BacktestService:
    """
    Сервис для работы с бэктестами.

    Координирует валидацию параметров, идемпотентность,
    создание задач и отправку в Kafka.
    """

    def __init__(self, db: AsyncSession, redis: Redis, user_id: UserID):
        """
        Инициализирует сервис бэктестов.

        Args:
            db: Асинхронная сессия базы данных
            redis: Клиент Redis
            user_id: UUID пользователя
        """
        self.db = db
        self.redis = redis
        self.user_id = user_id
        self.validator = BacktestValidator(db)
        self.idempotency_manager = IdempotencyManager(redis, user_id)

    async def submit_backtest(
        self,
        backtest_in: BacktestCreateRequest,
        idempotency_key: str | None,
        batch_id: BatchID | None = None,
        skip_validation: bool = False,
    ) -> BacktestJobs:
        """
        Основной метод для запуска бэктеста.

        Выполняет:
        1. Валидацию всех входных данных (если skip_validation=False)
        2. Проверку идемпотентности
        3. Проверку владения стратегией
        4. Создание задачи в БД
        5. Отправку сообщения в Kafka

        Args:
            backtest_in: Параметры бэктеста
            idempotency_key: Ключ идемпотентности
            batch_id: ID batch (если создается в составе группы)
            skip_validation: Пропустить валидацию (используется в batch после предварительной проверки)

        Returns:
            Созданная задача бэктеста

        Raises:
            HTTPException: При ошибках валидации или создания задачи
        """
        # 1. БИЗНЕС-ВАЛИДАЦИЯ
        if not skip_validation:
            log.info(
                "backtest.validation.started",
                user_id=str(self.user_id),
            )

            # Валидация тикера (async - проверяет существование)
            await self.validator.validate_ticker(backtest_in.ticker)

            # Валидация таймфрейма
            self.validator.validate_timeframe(backtest_in.timeframe)

            # Валидация дат и получение parsed дат
            parsed_start, parsed_end = self.validator.validate_date_range(
                backtest_in.start_date, backtest_in.end_date
            )

            # Валидация параметров симуляции
            simulation_params_dict = (
                backtest_in.simulation_params.model_dump()
                if backtest_in.simulation_params
                else {}
            )
            self.validator.validate_simulation_params(simulation_params_dict)

            log.info(
                "backtest.validation.completed",
                user_id=str(self.user_id),
            )
        else:
            # Валидация пропущена, но нужно распарсить даты
            parsed_start, parsed_end = self.validator.validate_date_range(
                backtest_in.start_date, backtest_in.end_date
            )

        # 2. Проверка идемпотентности
        request_hash = str(hash(backtest_in.model_dump_json()))
        existing_job_id = await self.idempotency_manager.check_idempotency(
            idempotency_key, request_hash
        )
        if existing_job_id:
            job = await crud_backtests.get_backtest_job_by_id(
                self.db,
                user_id=self.user_id,
                job_id=uuid.UUID(existing_job_id),
            )
            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Previously created job not found.",
                )
            return job

        # 3. Валидация владения стратегией
        strategy = await crud_strategies.get_strategy_by_id(
            self.db,
            user_id=self.user_id,
            strategy_id=backtest_in.strategy_id,
        )
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found or does not belong to the user.",
            )

        # 4. Проверка достаточности данных в ClickHouse
        if not skip_validation:
            has_sufficient_data, error_message = (
                await self.validator.check_data_sufficiency(
                    ticker=backtest_in.ticker,
                    timeframe=backtest_in.timeframe,
                    start_date=backtest_in.start_date,
                    end_date=backtest_in.end_date,
                    strategy_definition=strategy.definition,
                )
            )

            if not has_sufficient_data:
                # Для одиночных бэктестов - отдаем HTTP ошибку
                log.warning(
                    "backtest.rejected.insufficient_data",
                    ticker=backtest_in.ticker,
                    timeframe=backtest_in.timeframe,
                    period=f"{backtest_in.start_date} - {backtest_in.end_date}",
                    error=error_message,
                )

                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=error_message,
                )

        # 5. Создание задачи в БД
        try:
            job = await crud_backtests.create_backtest_job(
                self.db,
                user_id=self.user_id,
                backtest_in=backtest_in,
                strategy_snapshot=strategy.definition,
                parsed_start_date=parsed_start,
                parsed_end_date=parsed_end,
                batch_id=batch_id,
            )

            # commit перед отправкой в Kafka!
            await self.db.commit()
        except Exception as e:
            log.error("backtest.db.create.failed", error=str(e))
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create backtest job.",
            )

        # 6. Отправка в Kafka
        try:
            await kafka_service.send_backtest_request(job.id)
        except Exception as e:
            # Если Kafka недоступна, помечаем задачу как FAILED
            log.error("kafka.send.failed", job_id=str(job.id), error=str(e))
            await crud_backtests.update_job_status(
                self.db, job.id, JobStatus.FAILED, "Message broker unavailable"
            )
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Message broker is currently unavailable. Please try again later.",
            )

        # 7. Сохранение ключа идемпотентности
        await self.idempotency_manager.store_idempotency_key(
            idempotency_key, request_hash, job.id
        )

        return job
