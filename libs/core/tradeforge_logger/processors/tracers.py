# -*- coding: utf-8 -*-
"""Процессоры для интеграции с distributed tracing.

Этот модуль содержит процессоры для добавления trace_id и span_id из OpenTelemetry.
"""

from __future__ import annotations

from structlog.types import EventDict, WrappedLogger


def create_tracing_processor(enable_tracing: bool):
    """Создает процессор для добавления tracing информации.

    Args:
        enable_tracing: Включить ли интеграцию с OpenTelemetry.

    Returns:
        Процессор функция.
    """

    def processor(
        logger: WrappedLogger,
        method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        """Добавляет trace_id и span_id из OpenTelemetry.

        Args:
            logger: Logger instance.
            method_name: Имя метода логирования.
            event_dict: Event dictionary.

        Returns:
            Обогащенный event_dict с tracing информацией.
        """
        if not enable_tracing:
            return event_dict

        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span is not None:
                span_context = span.get_span_context()
                if span_context.is_valid:
                    event_dict["trace_id"] = format(
                        span_context.trace_id, "032x"
                    )
                    event_dict["span_id"] = format(
                        span_context.span_id, "016x"
                    )
        except ImportError:
            pass

        return event_dict

    return processor
