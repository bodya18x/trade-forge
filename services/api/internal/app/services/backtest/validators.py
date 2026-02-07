"""
Валидаторы параметров бэктестов.

Содержит методы проверки корректности входных данных.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_logger import get_logger

from app.crud import crud_clickhouse, crud_metadata
from app.database import get_clickhouse_client
from app.settings import settings

log = get_logger(__name__)


class BacktestValidator:
    """
    Валидатор параметров бэктестов.

    Проверяет корректность тикера, таймфрейма, диапазона дат,
    параметров симуляции и достаточность данных.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализирует валидатор.

        Args:
            db: Асинхронная сессия базы данных
        """
        self.db = db

    async def validate_ticker(self, ticker: str) -> None:
        """
        Валидация тикера.

        Проверяет длину, формат и существование тикера в системе.

        Args:
            ticker: Тикер для проверки

        Raises:
            HTTPException: Если тикер не прошел валидацию
        """
        if not ticker or not ticker.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ticker не может быть пустым",
            )

        ticker_cleaned = ticker.strip().upper()

        if len(ticker_cleaned) < settings.MIN_TICKER_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Тикер должен содержать минимум {settings.MIN_TICKER_LENGTH} символ",
            )

        if len(ticker_cleaned) > settings.MAX_TICKER_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Тикер не может превышать {settings.MAX_TICKER_LENGTH} символов",
            )

        # Проверяем что тикер содержит только допустимые символы
        if not re.match(r"^[A-Z0-9_-]+$", ticker_cleaned):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Тикер может содержать только буквы, цифры, дефисы и подчёркивания",
            )

        # Проверяем существование тикера в базе данных
        ticker_check = await crud_metadata.check_tickers_exist(
            self.db, [ticker_cleaned]
        )

        if not ticker_check.get(ticker_cleaned, False):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Тикер '{ticker}' не найден или неактивен в системе",
            )

    def validate_timeframe(self, timeframe: str) -> None:
        """
        Валидация таймфрейма.

        Проверяет что таймфрейм находится в списке допустимых.

        Args:
            timeframe: Таймфрейм для проверки

        Raises:
            HTTPException: Если таймфрейм не прошел валидацию
        """
        if not timeframe or timeframe not in settings.VALID_TIMEFRAMES:
            valid_timeframes_str = ", ".join(settings.VALID_TIMEFRAMES)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Недопустимый таймфрейм. Допустимые значения: {valid_timeframes_str}",
            )

    def validate_date_range(
        self, start_date: str, end_date: str
    ) -> tuple[datetime, datetime]:
        """
        Валидация диапазона дат для бэктеста.

        Проверяет:
        - Корректность формата дат
        - Что start_date < end_date
        - Что даты не в будущем

        Args:
            start_date: Дата начала в ISO формате
            end_date: Дата окончания в ISO формате

        Returns:
            Tuple с parsed датами (start, end)

        Raises:
            HTTPException: Если даты не прошли валидацию
        """
        # Парсинг дат
        try:
            if "T" in start_date:
                parsed_start = datetime.fromisoformat(
                    start_date.replace("Z", "+03:00")
                )
            else:
                parsed_start = datetime.fromisoformat(
                    start_date + "T00:00:00+03:00"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Неверный формат даты начала. Используйте ISO формат: YYYY-MM-DD или YYYY-MM-DDTHH:MM:SS",
            )

        try:
            if "T" in end_date:
                parsed_end = datetime.fromisoformat(
                    end_date.replace("Z", "+03:00")
                )
            else:
                parsed_end = datetime.fromisoformat(
                    end_date + "T23:59:59+03:00"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Неверный формат даты окончания. Используйте ISO формат: YYYY-MM-DD или YYYY-MM-DDTHH:MM:SS",
            )

        # Проверка логичности диапазона
        if parsed_start >= parsed_end:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Дата начала должна быть раньше даты окончания",
            )

        # Проверка что даты не в будущем
        now = datetime.now(parsed_start.tzinfo)
        if parsed_start > now:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Дата начала не может быть в будущем",
            )

        # Если дата окончания в будущем
        if parsed_end > now:
            # Если это сегодняшний день, просто смещаем дату
            if parsed_end.date() == now.date():
                parsed_end = parsed_end - timedelta(days=1)
            else:
                # Если дата действительно в будущем (не сегодня), возвращаем ошибку
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Дата окончания не может быть в будущем",
                )

        return parsed_start, parsed_end

    def validate_simulation_params(self, simulation_params: dict) -> None:
        """
        Валидация параметров симуляции.

        Проверяет корректность значений для торговой симуляции.

        Args:
            simulation_params: Словарь с параметрами симуляции

        Raises:
            HTTPException: Если параметры не прошли валидацию
        """
        if not simulation_params:
            return  # Параметры опциональны, будут использованы дефолтные

        # Валидация начального баланса
        initial_balance = simulation_params.get("initial_balance")
        if initial_balance is not None:
            if (
                not isinstance(initial_balance, (int, float))
                or initial_balance <= 0
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Начальный баланс должен быть положительным числом",
                )

            if initial_balance < settings.MIN_INITIAL_BALANCE:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Начальный баланс не может быть меньше {settings.MIN_INITIAL_BALANCE:,.0f}",
                )

            if initial_balance > settings.MAX_INITIAL_BALANCE:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Начальный баланс не может превышать {settings.MAX_INITIAL_BALANCE:,.0f}",
                )

        # Валидация комиссии
        commission_pct = simulation_params.get("commission_pct")
        if commission_pct is not None:
            if (
                not isinstance(commission_pct, (int, float))
                or commission_pct < 0
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Комиссия должна быть неотрицательным числом",
                )

            if commission_pct < settings.MIN_COMMISSION_PCT:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Комиссия не может быть меньше {settings.MIN_COMMISSION_PCT}%",
                )

            if commission_pct > settings.MAX_COMMISSION_PCT:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Комиссия не может превышать {settings.MAX_COMMISSION_PCT}%",
                )

        # Валидация размера позиции
        position_size_pct = simulation_params.get("position_size_pct")
        if position_size_pct is not None:
            if (
                not isinstance(position_size_pct, (int, float))
                or position_size_pct <= 0
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Размер позиции должен быть положительным числом",
                )

            if position_size_pct < settings.MIN_POSITION_SIZE_PCT:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Размер позиции не может быть меньше {settings.MIN_POSITION_SIZE_PCT}%",
                )

            if position_size_pct > settings.MAX_POSITION_SIZE_PCT:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Размер позиции не может превышать {settings.MAX_POSITION_SIZE_PCT}%",
                )

    async def check_data_sufficiency(
        self,
        ticker: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        strategy_definition: dict,
    ) -> tuple[bool, str | None]:
        """
        Проверяет достаточность данных с учетом lookback периода индикаторов.

        Args:
            ticker: Тикер
            timeframe: Таймфрейм
            start_date: Дата начала
            end_date: Дата окончания
            strategy_definition: AST определение стратегии

        Returns:
            Tuple (has_sufficient_data, error_message)
        """
        try:
            clickhouse_client = get_clickhouse_client()

            result = (
                await crud_clickhouse.check_data_availability_with_lookback(
                    clickhouse_client=clickhouse_client,
                    ticker=ticker,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    strategy_definition=strategy_definition,
                )
            )

            has_sufficient = result.get("has_sufficient_data", True)
            error_msg = result.get("error_message")

            log.info(
                "backtest.data_sufficiency.check.completed",
                ticker=ticker,
                timeframe=timeframe,
                period=f"{start_date} - {end_date}",
                has_sufficient_data=has_sufficient,
                max_lookback=result.get("max_lookback", 0),
                period_first_candle=result.get("period_first_candle"),
                period_last_candle=result.get("period_last_candle"),
                lookback_count=result.get("lookback_candles_count", 0),
            )

            return has_sufficient, error_msg

        except Exception as e:
            log.error(
                "backtest.data_sufficiency.check.failed",
                ticker=ticker,
                timeframe=timeframe,
                error=str(e),
                exc_info=True,
            )
            # В случае ошибки ClickHouse - не блокируем создание бэктеста
            return True, None
