"""
Асинхронный клиент для работы с MOEX ISS API.

Использует AsyncApiClient из внутренних библиотек с rate limiting.
"""

from __future__ import annotations

from typing import Any

from tradeforge_apiclient import AsyncApiClient, RateLimiter
from tradeforge_logger import get_logger

logger = get_logger(__name__)


class AsyncMoexApiClient(AsyncApiClient):
    """
    Асинхронный клиент для MOEX ISS API.

    Наследует AsyncApiClient из внутренних библиотек и добавляет
    методы для работы с конкретными эндпоинтами MOEX.
    """

    def __init__(
        self,
        rate_limit_requests: int,
        rate_limit_seconds: float,
        timeout: int = 10,
    ):
        """
        Инициализация клиента MOEX API.

        Args:
            rate_limit_requests: Макс. количество запросов за интервал
            rate_limit_seconds: Интервал для rate limiting (сек)
            timeout: Таймаут запросов (сек)
        """
        limiter = RateLimiter(rate_limit_requests, rate_limit_seconds)
        super().__init__(limiter)

        self.timeout = timeout
        self.logger = logger

    async def get_all_securities(self) -> list[dict[str, Any]]:
        """
        Получает список всех тикеров с доски TQBR.

        Returns:
            Список словарей с данными по тикерам
        """
        # TODO: Оставил ссылку на потом, когда будем собирать фьючерсы.
        # https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/securities.json
        url = (
            "https://iss.moex.com/iss/engines/stock/markets/"
            "shares/boards/TQBR/securities.json"
        )

        try:
            response = await self.get_page(
                url, json_format=True, timeout=self.timeout
            )
        except Exception as e:
            logger.error(
                "moex_client.get_securities_failed",
                error=str(e),
                exc_info=True,
            )
            return []

        if not response:
            logger.warning("moex_client.empty_securities_response")
            return []

        securities = response.get("securities", {})
        columns = securities.get("columns", [])
        data = securities.get("data", [])

        if not data or not columns:
            logger.warning("moex_client.no_securities_data")
            return []

        # Преобразуем в список словарей
        result = [dict(zip(columns, row)) for row in data]

        logger.debug(
            "moex_client.securities_fetched",
            count=len(result),
        )

        return result

    async def get_candles(
        self,
        ticker: str,
        interval: int,
        from_date: str,
    ) -> list[dict[str, Any]]:
        """
        Получает свечи для указанного тикера.

        Args:
            ticker: Алиас тикера (например, "SBER")
            interval: Значение interval для MOEX API (1, 10, 60, 24, 7, 31)
            from_date: Дата начала в формате "YYYY-MM-DD HH:MM:SS"

        Returns:
            Список словарей с данными свечей
        """
        url = (
            f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/"
            f"tqbr/securities/{ticker}/candles.json"
        )
        params = {"interval": interval, "from": from_date}

        try:
            response = await self.get_page(
                url,
                params=params,
                json_format=True,
                timeout=self.timeout,
            )
        except Exception as e:
            logger.error(
                "moex_client.get_candles_failed",
                ticker=ticker,
                interval=interval,
                from_date=from_date,
                error=str(e),
                exc_info=True,
            )
            return []

        if not response:
            logger.warning(
                "moex_client.empty_candles_response",
                ticker=ticker,
            )
            return []

        candles_info = response.get("candles", {})
        columns = candles_info.get("columns", [])
        data = candles_info.get("data", [])

        if not data or not columns:
            logger.debug(
                "moex_client.no_candles_data",
                ticker=ticker,
                interval=interval,
            )
            return []

        # Преобразуем в список словарей
        result = [dict(zip(columns, row)) for row in data]

        logger.debug(
            "moex_client.candles_fetched",
            ticker=ticker,
            interval=interval,
            count=len(result),
        )

        return result
