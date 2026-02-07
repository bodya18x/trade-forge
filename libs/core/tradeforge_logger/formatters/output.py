# -*- coding: utf-8 -*-
"""Форматтеры для вывода логов.

Этот модуль содержит форматтеры для JSON и Console вывода.
"""

from __future__ import annotations

import json
from typing import Any

from structlog.types import EventDict

# ============================================================================
# JSON Formatter
# ============================================================================


class JSONFormatter:
    """JSON форматтер для production логов.

    Создает компактный однострочный JSON для каждого лог-события.
    """

    def __init__(self, indent: int | None = None, sort_keys: bool = False):
        """Инициализация JSON форматтера.

        Args:
            indent: Отступ для pretty-printing (None для компактного вывода).
            sort_keys: Сортировать ли ключи.
        """
        self.indent = indent
        self.sort_keys = sort_keys

    def __call__(
        self, logger: Any, method_name: str, event_dict: EventDict
    ) -> str:
        """Форматирует event_dict в JSON строку.

        Args:
            logger: Logger instance.
            method_name: Имя метода логирования.
            event_dict: Event dictionary.

        Returns:
            JSON строка.
        """
        return json.dumps(
            event_dict,
            indent=self.indent,
            sort_keys=self.sort_keys,
            default=str,  # Конвертируем не-JSON типы в строки
            ensure_ascii=False,  # Поддержка Unicode
        )


# ============================================================================
# Console Formatter
# ============================================================================


class ConsoleFormatter:
    """Читаемый форматтер для development.

    Создает структурированный вывод с переносами строк и отступами.
    """

    # ANSI цветовые коды
    COLORS = {
        "debug": "\033[36m",  # Cyan
        "info": "\033[32m",  # Green
        "warning": "\033[33m",  # Yellow
        "error": "\033[31m",  # Red
        "critical": "\033[35m",  # Magenta
        "reset": "\033[0m",  # Reset
    }

    # Поля, которые не нужно выводить в "остальных полях"
    SKIP_FIELDS = {
        "timestamp",
        "level",
        "event",
        "logger",
    }

    def __init__(self, colors: bool = False, pad: int = 12):
        """Инициализация Console форматтера.

        Args:
            colors: Использовать ли ANSI цвета.
            pad: Отступ для выравнивания.
        """
        self.colors = colors
        self.pad = pad

    def _colorize(self, text: str, color_name: str) -> str:
        """Добавляет ANSI цвет к тексту.

        Args:
            text: Текст.
            color_name: Имя цвета.

        Returns:
            Окрашенный текст или оригинальный если colors=False.
        """
        if not self.colors:
            return text

        color = self.COLORS.get(color_name, "")
        reset = self.COLORS["reset"]
        return f"{color}{text}{reset}"

    def _format_value(self, value: Any, indent: int = 0) -> str:
        """Форматирует значение для вывода.

        Args:
            value: Значение.
            indent: Уровень отступа.

        Returns:
            Отформатированная строка.
        """
        indent_str = "  " * indent

        if isinstance(value, dict):
            lines = ["{"]
            for k, v in value.items():
                formatted_v = self._format_value(v, indent + 1)
                lines.append(f"{indent_str}  {k}: {formatted_v}")
            lines.append(f"{indent_str}}}")
            return "\n".join(lines)
        elif isinstance(value, (list, tuple)):
            if not value:
                return "[]"
            lines = ["["]
            for item in value:
                formatted_item = self._format_value(item, indent + 1)
                lines.append(f"{indent_str}  {formatted_item}")
            lines.append(f"{indent_str}]")
            return "\n".join(lines)
        else:
            return str(value)

    def __call__(
        self, logger: Any, method_name: str, event_dict: EventDict
    ) -> str:
        """Форматирует event_dict в читаемую строку.

        Args:
            logger: Logger instance.
            method_name: Имя метода логирования.
            event_dict: Event dictionary.

        Returns:
            Отформатированная строка.
        """
        # Извлекаем основные поля
        timestamp = event_dict.get("timestamp", "")
        level = event_dict.get("level", "info")
        event = event_dict.get("event", "")
        logger_name = event_dict.get("logger", "")

        # Форматируем timestamp (берем только время)
        if timestamp and "T" in timestamp:
            time_part = timestamp.split("T")[1].split("+")[0].split("Z")[0]
            # Обрезаем микросекунды до миллисекунд
            if "." in time_part:
                time_without_micro, micro = time_part.split(".")
                time_part = f"{time_without_micro}.{micro[:3]}"
        else:
            time_part = timestamp

        # Форматируем level
        level_str = level.upper().ljust(8)
        if self.colors:
            level_str = self._colorize(level_str, level)

        # Форматируем event
        event_str = str(event).ljust(self.pad * 3)
        if self.colors:
            event_str = self._colorize(event_str, "reset")

        # Формируем главную строку
        main_line = f"{time_part} [{level_str}] {event_str}"

        if logger_name:
            main_line += f" logger={logger_name}"

        lines = [main_line]

        # Добавляем остальные поля
        for key, value in event_dict.items():
            if key in self.SKIP_FIELDS:
                continue

            formatted_value = self._format_value(value)

            # Если значение многострочное, делаем отступ
            if "\n" in formatted_value:
                lines.append(f"    {key}:")
                for line in formatted_value.split("\n"):
                    lines.append(f"      {line}")
            else:
                lines.append(f"    {key}: {formatted_value}")

        return "\n".join(lines)


# ============================================================================
# Фабрика форматтеров
# ============================================================================


def get_formatter(
    enable_json: bool = True,
    enable_colors: bool = False,
) -> JSONFormatter | ConsoleFormatter:
    """Возвращает подходящий форматтер.

    Args:
        enable_json: Использовать JSON формат.
        enable_colors: Использовать цвета (только для Console).

    Returns:
        Экземпляр форматтера.

    Examples:
        >>> formatter = get_formatter(enable_json=True)
        >>> isinstance(formatter, JSONFormatter)
        True
        >>> formatter = get_formatter(enable_json=False, enable_colors=True)
        >>> isinstance(formatter, ConsoleFormatter)
        True
    """
    if enable_json:
        return JSONFormatter()
    else:
        return ConsoleFormatter(colors=enable_colors)
