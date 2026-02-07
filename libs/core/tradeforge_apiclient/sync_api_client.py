"""
Модуль предназначен для работы с запросами по API.

Реализованы следующие возможности:
    - Получение данных по API с синхронными запросами.
    - Обработка различных ошибок и исключений.
    - Ограничение числа запросов в заданный промежуток времени с использованием RateLimiter.
    - Логирование с возможностью добавления имени потока и полной трассировки стека.
    - Типизация с использованием аннотаций типов для повышения читаемости и надежности кода.
    - Вынесение всех числовых значений в константы для облегчения модификации и расширения.

Используемые пакеты:
    tradeforge_logger: логирование.
    time: измерение времени выполнения запросов.
    typing: использование типов для аннотаций.
    httpx: выполнение HTTP-запросов и обработка ошибок.
"""

from __future__ import annotations

import time
from types import TracebackType
from typing import Any, Dict, Optional, Union

import httpx
from tradeforge_logger import get_logger

from .base_client_mixin import ApiClientAbstract
from .helpers import HTTPMethod
from .limiter import RateLimiter


class SyncApiClient(ApiClientAbstract):
    """Класс для работы с запросами по API."""

    def __init__(self, limiter: Optional[RateLimiter] = None) -> None:
        """Инициализация класса.

        Args:
            limiter (Optional[RateLimiter]): Лимитер запросов. Если не задан,
                то создается внутренний лимитер.
        """
        self.limiter = limiter or RateLimiter(
            self.RATE_LIMIT_REQUESTS, self.RATE_LIMIT_SECONDS
        )
        self.client = httpx.Client(follow_redirects=self.FOLLOW_REDIRECTS)
        self.logger = get_logger(__name__)

    def close(self) -> None:
        """Закрытие HTTP-клиента."""
        try:
            self.client.close()
            self.logger.debug("apiclient.client_closed")
        except Exception as e:
            self.logger.error(
                "apiclient.close_error",
                error=str(e),
                exception_type=type(e).__name__,
            )

    def __enter__(self) -> SyncApiClient:
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def get_page(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        method: str = "get",
        limit_request: bool = True,
        timeout: Optional[int] = None,
        json_format: bool = False,
        if_error_return: bool = False,
        json_data: Optional[Dict[str, Any]] = None,
        log_fails: bool = True,
    ) -> Union[Dict[str, Any], httpx.Response, None]:
        """Выполняет HTTP-запрос с обработкой ошибок и ограничением числа запросов.

        Аргументы:
            url (str): URL для выполнения запроса.
            params (Optional[Dict[str, Any]]): Параметры запроса.
            headers (Optional[Dict[str, str]]): Заголовки запроса.
            method (str): Метод HTTP-запроса (get, post и т.д.).
            limit_request (bool): Ограничивать ли число запросов в секунду.
            timeout (Optional[int]): Таймаут для запроса.
            json_format (bool): Преобразовывать ли ответ в формат JSON.
            if_error_return (bool): Возвращать ли ответ в случае ошибки.
            json_data (Optional[Dict[str, Any]]): Данные для JSON-запроса.
            log_fails (bool): Логировать ли текст ответа при ошибках.

        Returns:
            Union[Dict[str, Any], httpx.Response, None]: Ответ сервера или None в случае неудачи.
        """
        if method.lower() not in HTTPMethod.list_methods():
            raise ValueError(f"Unsupported HTTP method: {method}")

        retry_count = 0
        response: Optional[httpx.Response] = None
        timeout_value = timeout if timeout is not None else self.TIMEOUT

        args = {
            "url": url,
            "params": params,
            "headers": headers,
            "timeout": timeout_value,
        }
        if json_data:
            args["json"] = json_data

        while retry_count < self.MAX_RETRY_COUNT:
            if limit_request:
                self.limiter.acquire()

            try:
                self.logger.debug(
                    "apiclient.request_started",
                    url=url,
                    method=method,
                    retry_count=retry_count,
                    timeout=timeout_value,
                    has_params=params is not None,
                    has_json_data=json_data is not None,
                )

                time_start = time.time()
                response = getattr(self.client, method)(**args)
                time_end = round(time.time() - time_start, 3)
                response.raise_for_status()

                content_len = len(response.content)
                self.logger.debug(
                    "apiclient.response_received",
                    url=url,
                    method=method,
                    status_code=response.status_code,
                    response_size_bytes=content_len,
                    request_time_seconds=time_end,
                )

                if json_format:
                    return response.json()
                else:
                    return response

            except Exception as err:
                result = self._handle_exception(
                    logger=self.logger,
                    err=err,
                    retry_count=retry_count,
                    url=url,
                    method=method,
                    response=response,
                    if_error_return=if_error_return,
                    log_fails=log_fails,
                )
                if result is True:
                    retry_count += 1
                    continue  # Повторить запрос
                elif isinstance(result, httpx.Response):
                    return result  # Вернуть ответ при ошибке
                else:
                    break  # Не повторять попытку

        # Если все попытки исчерпаны
        self.logger.error(
            "apiclient.max_retries_exceeded",
            url=url,
            method=method,
            max_retry_count=self.MAX_RETRY_COUNT,
        )
        return None
