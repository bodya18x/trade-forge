from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Deque, Optional


class RateLimiter:
    """Простой ограничитель скорости запросов.

    Этот класс позволяет ограничить количество вызовов за определенный период времени,
    предоставляя методы для синхронного и асинхронного использования.

    Атрибуты:
        max_calls (int): Максимальное количество вызовов за период.
        period (float): Период времени в секундах.
        calls (Deque[float]): Дек для хранения временных меток вызовов.
        lock (threading.Lock): Блокировка для обеспечения потокобезопасности в синхронном режиме.
    """

    def __init__(self, max_calls: int, period: float) -> None:
        self.max_calls = max_calls
        self.period = period
        self.calls: Deque[float] = deque(maxlen=max_calls)
        self.lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None

    @property
    def async_lock(self) -> asyncio.Lock:
        """Lazy initialization для asyncio.Lock, чтобы избежать проблем с event loop.

        Returns:
            asyncio.Lock: Асинхронная блокировка для потокобезопасности.
        """
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def acquire(self) -> None:
        """Синхронный метод для ограничения скорости вызовов.

        Блокирует выполнение потока, если количество вызовов превышает установленный лимит.
        Добавляет текущую временную метку, если лимит не превышен.
        """
        with self.lock:
            now = time.time()
            # Удаляем вызовы, которые вышли за пределы периода
            # Используем popleft() чтобы не создавать новый deque (утечка памяти)
            while self.calls and self.calls[0] <= now - self.period:
                self.calls.popleft()
            if len(self.calls) >= self.max_calls:
                sleep_time = self.calls[0] + self.period - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
            self.calls.append(time.time())

    async def acquire_async(self) -> None:
        """Асинхронный метод для ограничения скорости вызовов.

        Приостанавливает выполнение корутины, если количество вызовов превышает установленный лимит.
        Добавляет текущую временную метку, если лимит не превышен.
        """
        async with self.async_lock:
            now = time.time()
            # Удаляем вызовы, которые вышли за пределы периода
            # Используем popleft() чтобы не создавать новый deque (утечка памяти)
            while self.calls and self.calls[0] <= now - self.period:
                self.calls.popleft()
            if len(self.calls) >= self.max_calls:
                sleep_time = self.calls[0] + self.period - now
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            self.calls.append(time.time())
