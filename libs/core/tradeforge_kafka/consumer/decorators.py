"""
Декораторы для обработчиков сообщений в AsyncKafkaConsumer.

Предоставляет удобные утилиты для retry логики, circuit breaker и т.д.
"""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Awaitable, Callable, TypeVar

from tradeforge_logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Декоратор для retry логики с exponential backoff.

    Используется для добавления дополнительных retry НА УРОВНЕ МЕТОДА,
    помимо встроенного retry в AsyncKafkaConsumer.

    Args:
        max_attempts: Максимальное количество попыток
        delay_seconds: Начальная задержка между попытками
        backoff_multiplier: Множитель для exponential backoff
        exceptions: Кортеж исключений для retry (по умолчанию - все)

    Example:
        ```python
        class MyConsumer(AsyncKafkaConsumer[MyMessage]):
            @retry(max_attempts=5, delay_seconds=2.0)
            async def on_message(self, msg: KafkaMessage[MyMessage]) -> None:
                # Этот метод будет повторяться до 5 раз
                await self.external_api.call(msg.value)
        ```
    """

    def decorator(
        func: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception: Exception | None = None
            current_delay = delay_seconds

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt < max_attempts:
                        logger.warning(
                            "decorator.retry.attempt_failed",
                            function=func.__name__,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            error=str(e),
                            next_delay=current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_multiplier
                    else:
                        logger.error(
                            "decorator.retry.max_attempts_exceeded",
                            function=func.__name__,
                            max_attempts=max_attempts,
                            error=str(e),
                        )

            # Пробрасываем последнее исключение
            raise last_exception

        return wrapper

    return decorator


def timeout(
    seconds: float,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Декоратор для ограничения времени выполнения метода.

    Args:
        seconds: Максимальное время выполнения в секундах

    Example:
        ```python
        class MyConsumer(AsyncKafkaConsumer[MyMessage]):
            @timeout(30.0)  # Максимум 30 секунд на обработку
            async def on_message(self, msg: KafkaMessage[MyMessage]) -> None:
                await self.slow_operation(msg.value)
        ```

    Raises:
        asyncio.TimeoutError: Если метод не завершился за указанное время
    """

    def decorator(
        func: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs), timeout=seconds
                )
            except asyncio.TimeoutError:
                logger.error(
                    "decorator.timeout.exceeded",
                    function=func.__name__,
                    timeout_seconds=seconds,
                )
                raise

        return wrapper

    return decorator


def log_execution_time(
    log_level: str = "info", threshold_ms: float | None = None
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Декоратор для логирования времени выполнения метода.

    Args:
        log_level: Уровень логирования ("debug", "info", "warning", "error")
        threshold_ms: Логировать только если время превышает порог (опционально)

    Example:
        ```python
        class MyConsumer(AsyncKafkaConsumer[MyMessage]):
            @log_execution_time(threshold_ms=1000)  # Лог только если > 1s
            async def on_message(self, msg: KafkaMessage[MyMessage]) -> None:
                await self.process(msg.value)
        ```
    """

    def decorator(
        func: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            start_time = asyncio.get_event_loop().time()

            try:
                result = await func(*args, **kwargs)
                return result

            finally:
                execution_time_ms = (
                    asyncio.get_event_loop().time() - start_time
                ) * 1000

                # Логируем только если превышен порог (если задан)
                if threshold_ms is None or execution_time_ms > threshold_ms:
                    log_func = getattr(logger, log_level)
                    log_func(
                        "decorator.execution_time",
                        function=func.__name__,
                        execution_time_ms=round(execution_time_ms, 2),
                    )

        return wrapper

    return decorator


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    expected_exception: type[Exception] = Exception,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Декоратор для реализации Circuit Breaker паттерна.

    Предотвращает вызов метода после N последовательных ошибок.
    Автоматически "закрывает" circuit после recovery_timeout.

    States:
        - CLOSED: Нормальная работа
        - OPEN: Circuit открыт, вызовы блокируются
        - HALF_OPEN: Тестовое состояние после таймаута

    Args:
        failure_threshold: Количество ошибок до открытия circuit
        recovery_timeout: Время до попытки восстановления (секунды)
        expected_exception: Тип исключения для отслеживания

    Example:
        ```python
        class MyConsumer(AsyncKafkaConsumer[MyMessage]):
            @circuit_breaker(failure_threshold=3, recovery_timeout=30.0)
            async def on_message(self, msg: KafkaMessage[MyMessage]) -> None:
                # Если external API упадет 3 раза подряд,
                # circuit откроется и блокирует вызовы на 30 секунд
                await self.external_api.call(msg.value)
        ```

    Raises:
        CircuitBreakerOpenError: Если circuit открыт
    """

    class CircuitBreakerState:
        def __init__(self):
            self.failure_count = 0
            self.last_failure_time: float | None = None
            self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    state = CircuitBreakerState()

    def decorator(
        func: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            current_time = asyncio.get_event_loop().time()

            # Проверяем состояние circuit
            if state.state == "OPEN":
                # Проверяем, прошло ли время восстановления
                if (
                    state.last_failure_time
                    and current_time - state.last_failure_time
                    > recovery_timeout
                ):
                    state.state = "HALF_OPEN"
                    logger.info(
                        "decorator.circuit_breaker.half_open",
                        function=func.__name__,
                    )
                else:
                    logger.warning(
                        "decorator.circuit_breaker.open",
                        function=func.__name__,
                        failure_count=state.failure_count,
                    )
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is OPEN for {func.__name__}"
                    )

            try:
                result = await func(*args, **kwargs)

                # Успех - сбрасываем счетчик
                if state.state == "HALF_OPEN":
                    logger.info(
                        "decorator.circuit_breaker.closed",
                        function=func.__name__,
                    )
                    state.state = "CLOSED"

                state.failure_count = 0
                return result

            except expected_exception as e:
                state.failure_count += 1
                state.last_failure_time = current_time

                logger.warning(
                    "decorator.circuit_breaker.failure",
                    function=func.__name__,
                    failure_count=state.failure_count,
                    threshold=failure_threshold,
                    error=str(e),
                )

                # Открываем circuit если достигнут порог
                if state.failure_count >= failure_threshold:
                    state.state = "OPEN"
                    logger.error(
                        "decorator.circuit_breaker.opened",
                        function=func.__name__,
                        failure_count=state.failure_count,
                        recovery_timeout=recovery_timeout,
                    )

                raise

        return wrapper

    return decorator


class CircuitBreakerOpenError(Exception):
    """Исключение при открытом circuit breaker."""

    pass
