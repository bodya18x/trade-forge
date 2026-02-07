"""
Валидация групповых бэктестов.

Содержит логику предварительной валидации всех задач в batch.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_logger import get_logger
from tradeforge_schemas import BacktestCreateRequest

from app.crud import crud_clickhouse, crud_strategies
from app.database import get_clickhouse_client
from app.services.backtest import BacktestService

log = get_logger(__name__)


class BatchValidator:
    """
    Валидатор групповых бэктестов.

    Проверяет все задачи в batch перед созданием.
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        backtest_service: BacktestService,
    ):
        """
        Инициализирует валидатор batch.

        Args:
            db: Асинхронная сессия базы данных
            user_id: UUID пользователя
            backtest_service: Сервис бэктестов для делегирования валидации
        """
        self.db = db
        self.user_id = user_id
        self.backtest_service = backtest_service

    async def validate_all_backtests(
        self, backtests: list[dict[str, Any]]
    ) -> None:
        """
        Валидирует все бэктесты в batch.

        Собирает все ошибки валидации перед созданием чего-либо.
        При наличии хотя бы одной ошибки выбрасывает HTTPException.

        Args:
            backtests: Список параметров для каждого бэктеста

        Raises:
            HTTPException: При ошибках валидации любой задачи (HTTP 422)
        """
        validation_errors = []

        for idx, backtest_params in enumerate(backtests):
            try:
                # Парсим Pydantic модель
                backtest_request = BacktestCreateRequest(**backtest_params)

                # Валидируем тикер (проверяет существование в БД)
                await self.backtest_service.validator.validate_ticker(
                    backtest_request.ticker
                )

                # Валидируем таймфрейм
                self.backtest_service.validator.validate_timeframe(
                    backtest_request.timeframe
                )

                # Валидируем даты
                self.backtest_service.validator.validate_date_range(
                    backtest_request.start_date, backtest_request.end_date
                )

                # Валидируем параметры симуляции
                simulation_params_dict = (
                    backtest_request.simulation_params.model_dump()
                    if backtest_request.simulation_params
                    else {}
                )
                self.backtest_service.validator.validate_simulation_params(
                    simulation_params_dict
                )

                # Валидируем владение стратегией
                strategy = await crud_strategies.get_strategy_by_id(
                    self.db,
                    user_id=self.user_id,
                    strategy_id=backtest_request.strategy_id,
                )
                if not strategy:
                    raise ValueError(
                        f"Стратегия не найдена или не принадлежит пользователю"
                    )

            except Exception as e:
                # Собираем информацию об ошибке
                error_detail = {
                    "index": idx,
                    "ticker": backtest_params.get("ticker", "UNKNOWN"),
                    "timeframe": backtest_params.get("timeframe", "UNKNOWN"),
                    "error": str(e),
                }
                validation_errors.append(error_detail)

        # Если есть хоть одна ошибка валидации → отклоняем весь batch
        if validation_errors:
            log.warning(
                "batch.validation.failed",
                user_id=str(self.user_id),
                total_backtests=len(backtests),
                failed_validations=len(validation_errors),
                errors=validation_errors,
            )

            # Формируем читаемое сообщение об ошибках
            error_messages = []
            for err in validation_errors:
                error_messages.append(
                    f"Бэктест #{err['index'] + 1} (ticker: {err['ticker']}, timeframe: {err['timeframe']}): {err['error']}"
                )

            detail_message = (
                f"Batch validation failed. {len(validation_errors)} из {len(backtests)} бэктестов не прошли валидацию:\n"
                + "\n".join(error_messages)
            )

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=detail_message,
            )

    async def check_data_sufficiency_for_all(
        self, backtests: list[dict[str, Any]]
    ) -> dict[tuple[str, str, str, str], dict[str, Any]]:
        """
        Проверяет достаточность данных для всех бэктестов в batch.

        Args:
            backtests: Список параметров для каждого бэктеста

        Returns:
            Словарь с результатами проверки для каждой комбинации параметров
            Ключ: (ticker, timeframe, start_date, end_date)
            Значение: результат проверки данных
        """
        log.info(
            "batch.validation.success",
            user_id=str(self.user_id),
            total_count=len(backtests),
        )

        clickhouse_client = get_clickhouse_client()
        data_sufficiency_results = {}

        for backtest_params in backtests:
            # Получаем стратегию для проверки индикаторов
            strategy = await crud_strategies.get_strategy_by_id(
                self.db,
                user_id=self.user_id,
                strategy_id=backtest_params["strategy_id"],
            )

            if not strategy:
                # Стратегия не найдена (не должно случиться после валидации)
                data_sufficiency_results[
                    (
                        backtest_params["ticker"],
                        backtest_params["timeframe"],
                        backtest_params["start_date"],
                        backtest_params["end_date"],
                    )
                ] = {
                    "has_sufficient_data": False,
                    "error_message": "Стратегия не найдена",
                }
                continue

            # Проверяем достаточность данных с учетом lookback
            result = (
                await crud_clickhouse.check_data_availability_with_lookback(
                    clickhouse_client=clickhouse_client,
                    ticker=backtest_params["ticker"],
                    timeframe=backtest_params["timeframe"],
                    start_date=backtest_params["start_date"],
                    end_date=backtest_params["end_date"],
                    strategy_definition=strategy.definition,
                )
            )

            data_sufficiency_results[
                (
                    backtest_params["ticker"],
                    backtest_params["timeframe"],
                    backtest_params["start_date"],
                    backtest_params["end_date"],
                )
            ] = result

        return data_sufficiency_results
