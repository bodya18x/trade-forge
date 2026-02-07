from __future__ import annotations

import json
import traceback
from abc import ABC
from typing import Any, Optional, Tuple, Union

import httpx


class ApiClientAbstract(ABC):
    """Абстрактный класс с общими настройками и методами для работы с API-клиентами.

    Атрибуты:
        RATE_LIMIT_SECONDS: Интервал времени для ограничения числа запросов.
        RATE_LIMIT_REQUESTS: Максимальное число запросов за интервал RATE_LIMIT_SECONDS.
        MAX_RETRY_COUNT: Максимальное количество попыток выполнить запрос.
        TIMEOUT: Таймаут для HTTP-запросов.
        RETRY_STATUS_CODES: Список статусов ответов для повторного запроса
        RETRYABLE_EXCEPTIONS: Кортеж ошибок для повторной обработки
        FOLLOW_REDIRECTS: Разрешены ли редиректы при запросах
    """

    # Константы для настройки клиента
    RATE_LIMIT_SECONDS: float = 1.0
    RATE_LIMIT_REQUESTS: int = 5
    MAX_RETRY_COUNT: int = 5
    TIMEOUT: int = 60
    RETRY_STATUS_CODES: list[int] = [500, 501, 502, 503, 504]
    RETRYABLE_EXCEPTIONS: Tuple = (
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.RemoteProtocolError,
        httpx.ReadError,
    )
    FOLLOW_REDIRECTS: bool = False

    def _handle_exception(
        self,
        logger: Any,
        err: Exception,
        retry_count: int,
        url: str,
        method: str,
        response: Optional[httpx.Response],
        if_error_return: bool,
        log_fails: bool,
    ) -> Union[bool, httpx.Response, None]:
        """Обрабатывает исключения, возникающие во время выполнения HTTP-запросов.

        Этот метод анализирует тип исключения и принимает решение о дальнейших действиях:
        повторить попытку запроса, вернуть ответ при ошибке, либо прекратить попытки.

        Аргументы:
            logger: Логгер для структурированного логирования.
            err (Exception): Исключение, возникшее во время выполнения запроса.
            retry_count (int): Текущий номер попытки выполнения запроса.
            url (str): URL запроса.
            method (str): HTTP метод.
            response (Optional[httpx.Response]): Ответ от сервера, если он был получен.
            if_error_return (bool): Флаг, указывающий, следует ли возвращать ответ при ошибке статуса HTTP.
            log_fails (bool): Флаг, указывающий, следует ли логировать содержимое ответа при ошибках.

        Returns:
            Union[bool, httpx.Response, None]:
                - True: если необходимо повторить попытку запроса.
                - httpx.Response: если `if_error_return` установлено в `True` и необходимо вернуть ответ при ошибке статуса HTTP.
                - False или None: если не следует повторять попытку и метод должен завершиться.

        Примечание:
            Этот метод помогает централизованно обрабатывать различные исключения и определить,
            следует ли повторять попытку запроса или нет, что упрощает код методов `get_page` в клиентах.
        """
        if isinstance(err, self.RETRYABLE_EXCEPTIONS):
            logger.warning(
                "apiclient.retryable_exception",
                exception_type=type(err).__name__,
                retry_count=retry_count,
                url=url,
                method=method,
            )
            return True  # Повторить попытку

        elif isinstance(err, httpx.HTTPStatusError):
            status_code = err.response.status_code
            if status_code in self.RETRY_STATUS_CODES:
                logger.warning(
                    "apiclient.http_status_error_retry",
                    status_code=status_code,
                    retry_count=retry_count,
                    url=url,
                    method=method,
                )
                return True  # Повторить попытку
            else:
                logger.error(
                    "apiclient.http_status_error",
                    status_code=status_code,
                    error=str(err),
                    url=url,
                    method=method,
                )
                if if_error_return:
                    return err.response  # Вернуть ответ при ошибке
                return False  # Не повторять попытку

        elif isinstance(err, json.JSONDecodeError):
            logger.error(
                "apiclient.json_decode_error",
                error=str(err),
                url=url,
                method=method,
            )
            if log_fails and response:
                logger.debug(
                    "apiclient.response_content",
                    response_text=response.text[:1000],  # Первые 1000 символов
                    url=url,
                )
            return False  # Не повторять попытку

        elif isinstance(err, httpx.RequestError):
            logger.error(
                "apiclient.request_error",
                error=str(err),
                exception_type=type(err).__name__,
                url=url,
                method=method,
                traceback=traceback.format_exc(),
            )
            return True  # Повторить попытку

        else:
            logger.exception(
                "apiclient.unexpected_error",
                error=str(err),
                exception_type=type(err).__name__,
                url=url,
                method=method,
            )
            return False  # Не повторять попытку
