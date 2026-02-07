"""
Метрики для Consumer и Producer.

Собирает статистику обработки сообщений для observability.
В будущем можно интегрировать с Prometheus.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ConsumerMetrics:
    """
    Метрики для Kafka Consumer.

    Attributes:
        total_processed: Всего обработано сообщений
        total_errors: Всего ошибок
        total_validation_errors: Ошибок валидации Pydantic
        total_retries: Всего retry попыток
        total_dlq_sent: Отправлено в DLQ
        processing_times: Очередь времен обработки (для расчета avg/p95)
        started_at: Время запуска consumer
        current_processing: Количество сообщений в обработке сейчас
        max_concurrent_reached: Максимальное достигнутое количество параллельных обработок
    """

    total_processed: int = 0
    total_errors: int = 0
    total_validation_errors: int = 0
    total_retries: int = 0
    total_dlq_sent: int = 0
    processing_times: deque[float] = field(
        default_factory=lambda: deque(maxlen=10000)
    )
    started_at: float = field(default_factory=time.time)
    current_processing: int = 0
    max_concurrent_reached: int = 0

    def record_success(self, processing_time_ms: float) -> None:
        """
        Записывает успешную обработку сообщения.

        Args:
            processing_time_ms: Время обработки в миллисекундах
        """
        self.total_processed += 1
        self.processing_times.append(processing_time_ms)

    def record_error(self) -> None:
        """Записывает ошибку обработки."""
        self.total_errors += 1

    def record_validation_error(self) -> None:
        """Записывает ошибку валидации."""
        self.total_validation_errors += 1
        self.total_errors += 1

    def record_retry(self) -> None:
        """Записывает retry попытку."""
        self.total_retries += 1

    def record_dlq_sent(self) -> None:
        """Записывает отправку в DLQ."""
        self.total_dlq_sent += 1

    def record_processing_started(self) -> None:
        """Записывает начало обработки сообщения (для параллельности)."""
        self.current_processing += 1
        if self.current_processing > self.max_concurrent_reached:
            self.max_concurrent_reached = self.current_processing

    def record_processing_finished(self) -> None:
        """Записывает завершение обработки сообщения (для параллельности)."""
        self.current_processing = max(0, self.current_processing - 1)

    def get_avg_processing_time(self) -> float:
        """
        Вычисляет среднее время обработки.

        Returns:
            Среднее время в миллисекундах, 0.0 если нет данных
        """
        if not self.processing_times:
            return 0.0
        return sum(self.processing_times) / len(self.processing_times)

    def get_p95_processing_time(self) -> float:
        """
        Вычисляет 95-й перцентиль времени обработки.

        Returns:
            P95 время в миллисекундах, 0.0 если нет данных
        """
        if not self.processing_times:
            return 0.0
        sorted_times = sorted(self.processing_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def get_p99_processing_time(self) -> float:
        """
        Вычисляет 99-й перцентиль времени обработки.

        Returns:
            P99 время в миллисекундах, 0.0 если нет данных
        """
        if not self.processing_times:
            return 0.0
        sorted_times = sorted(self.processing_times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def get_error_rate(self) -> float:
        """
        Вычисляет процент ошибок.

        Returns:
            Процент ошибок (0.0-1.0)
        """
        total = self.total_processed + self.total_errors
        if total == 0:
            return 0.0
        return self.total_errors / total

    def get_uptime_seconds(self) -> float:
        """
        Вычисляет время работы consumer.

        Returns:
            Uptime в секундах
        """
        return time.time() - self.started_at

    def get_throughput(self) -> float:
        """
        Вычисляет пропускную способность (сообщений/секунда).

        Returns:
            Количество сообщений в секунду
        """
        uptime = self.get_uptime_seconds()
        if uptime == 0:
            return 0.0
        return self.total_processed / uptime

    def to_dict(self) -> dict:
        """
        Экспортирует метрики в словарь для логирования/мониторинга.

        Returns:
            Словарь со всеми метриками
        """
        return {
            "total_processed": self.total_processed,
            "total_errors": self.total_errors,
            "total_validation_errors": self.total_validation_errors,
            "total_retries": self.total_retries,
            "total_dlq_sent": self.total_dlq_sent,
            "avg_processing_time_ms": round(self.get_avg_processing_time(), 2),
            "p95_processing_time_ms": round(self.get_p95_processing_time(), 2),
            "p99_processing_time_ms": round(self.get_p99_processing_time(), 2),
            "error_rate": round(self.get_error_rate(), 4),
            "uptime_seconds": round(self.get_uptime_seconds(), 2),
            "throughput_msg_per_sec": round(self.get_throughput(), 2),
            "current_processing": self.current_processing,
            "max_concurrent_reached": self.max_concurrent_reached,
        }


@dataclass
class ProducerMetrics:
    """
    Метрики для Kafka Producer.

    Attributes:
        total_sent: Всего отправлено сообщений
        total_errors: Всего ошибок отправки
        send_times: Очередь времен отправки (для расчета avg/p95)
        started_at: Время запуска producer
    """

    total_sent: int = 0
    total_errors: int = 0
    send_times: deque[float] = field(
        default_factory=lambda: deque(maxlen=1000)
    )
    started_at: float = field(default_factory=time.time)

    def record_success(self, send_time_ms: float) -> None:
        """
        Записывает успешную отправку.

        Args:
            send_time_ms: Время отправки в миллисекундах
        """
        self.total_sent += 1
        self.send_times.append(send_time_ms)

    def record_error(self) -> None:
        """Записывает ошибку отправки."""
        self.total_errors += 1

    def get_avg_send_time(self) -> float:
        """
        Вычисляет среднее время отправки.

        Returns:
            Среднее время в миллисекундах, 0.0 если нет данных
        """
        if not self.send_times:
            return 0.0
        return sum(self.send_times) / len(self.send_times)

    def get_p95_send_time(self) -> float:
        """
        Вычисляет 95-й перцентиль времени отправки.

        Returns:
            P95 время в миллисекундах, 0.0 если нет данных
        """
        if not self.send_times:
            return 0.0
        sorted_times = sorted(self.send_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def get_error_rate(self) -> float:
        """
        Вычисляет процент ошибок.

        Returns:
            Процент ошибок (0.0-1.0)
        """
        total = self.total_sent + self.total_errors
        if total == 0:
            return 0.0
        return self.total_errors / total

    def get_uptime_seconds(self) -> float:
        """
        Вычисляет время работы producer.

        Returns:
            Uptime в секундах
        """
        return time.time() - self.started_at

    def get_throughput(self) -> float:
        """
        Вычисляет пропускную способность (сообщений/секунда).

        Returns:
            Количество сообщений в секунду
        """
        uptime = self.get_uptime_seconds()
        if uptime == 0:
            return 0.0
        return self.total_sent / uptime

    def to_dict(self) -> dict:
        """
        Экспортирует метрики в словарь для логирования/мониторинга.

        Returns:
            Словарь со всеми метриками
        """
        return {
            "total_sent": self.total_sent,
            "total_errors": self.total_errors,
            "avg_send_time_ms": round(self.get_avg_send_time(), 2),
            "p95_send_time_ms": round(self.get_p95_send_time(), 2),
            "error_rate": round(self.get_error_rate(), 4),
            "uptime_seconds": round(self.get_uptime_seconds(), 2),
            "throughput_msg_per_sec": round(self.get_throughput(), 2),
        }


class MetricsCollector(Protocol):
    """
    Протокол для кастомных сборщиков метрик.

    Позволяет интегрировать с Prometheus, Grafana и т.д.

    Example:
        ```python
        class PrometheusCollector:
            def on_message_processed(self, ctx: dict) -> None:
                prometheus_counter.inc()
                prometheus_histogram.observe(ctx['processing_time_ms'])
        ```
    """

    def on_message_received(self, context: dict) -> None:
        """Вызывается при получении сообщения."""
        ...

    def on_message_processed(self, context: dict, success: bool) -> None:
        """Вызывается после обработки сообщения."""
        ...

    def on_message_sent(self, context: dict, success: bool) -> None:
        """Вызывается после отправки сообщения."""
        ...
