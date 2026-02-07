"""
Извлечение индикаторов из AST-дерева стратегий.

Этот модуль предоставляет функционал для рекурсивного обхода
AST стратегии и извлечения всех используемых индикаторов.
"""

from __future__ import annotations

from typing import Any


class IndicatorExtractor:
    """
    Извлекает ключи индикаторов из AST-дерева стратегии.

    Рекурсивно обходит определение стратегии и собирает
    все используемые ключи индикаторов.
    """

    # Суффиксы значений индикаторов, которые нужно удалить для получения базового ключа
    VALUE_SUFFIXES = {
        "value",
        "direction",
        "long",
        "short",
        "macd",
        "signal",
        "hist",
        "k",
        "d",
    }

    def extract_indicator_keys(self, definition: dict) -> set[str]:
        """
        Рекурсивно извлекает все ключи индикаторов из определения стратегии.

        Args:
            definition: AST-дерево стратегии (словарь)

        Returns:
            Множество полных ключей индикаторов

        Example:
            >>> extractor = IndicatorExtractor()
            >>> definition = {"entry_conditions": {"type": "INDICATOR_VALUE", "key": "ema_timeperiod_12_value"}}
            >>> extractor.extract_indicator_keys(definition)
            {'ema_timeperiod_12_value'}
        """
        required_keys: set[str] = set()

        def dive(node: Any) -> None:
            """Рекурсивно обходит AST и собирает ключи индикаторов."""
            if isinstance(node, dict):
                node_type = node.get("type")

                # Извлекаем ключи из разных типов узлов
                if node_type in ("INDICATOR_VALUE", "PREV_INDICATOR_VALUE"):
                    key = node.get("key")
                    if key:
                        required_keys.add(key)

                elif node_type == "SUPER_TREND_FLIP":
                    key = node.get("indicator_key")
                    if key:
                        required_keys.add(key)

                elif node_type == "INDICATOR_BASED":
                    for key_field in ["buy_value_key", "sell_value_key"]:
                        key = node.get(key_field)
                        if key:
                            required_keys.add(key)

                # Рекурсивно обходим вложенные узлы
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        dive(value)

            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, dict):
                        dive(item)

        dive(definition)
        required_keys.discard(None)
        return required_keys

    def extract_base_keys(self, full_keys: set[str]) -> set[str]:
        """
        Конвертирует полные ключи индикаторов в базовые (без суффиксов значений).

        Args:
            full_keys: Множество полных ключей индикаторов

        Returns:
            Множество базовых ключей индикаторов

        Example:
            >>> extractor = IndicatorExtractor()
            >>> extractor.extract_base_keys({'ema_timeperiod_12_value', 'rsi_timeperiod_14_value'})
            {'ema_timeperiod_12', 'rsi_timeperiod_14'}
        """
        base_keys: set[str] = set()

        for key in full_keys:
            if not isinstance(key, str):
                continue

            parts = key.split("_")

            # Проверяем, заканчивается ли ключ на известный суффикс
            if len(parts) > 1 and parts[-1] in self.VALUE_SUFFIXES:
                # Удаляем суффикс
                base_keys.add("_".join(parts[:-1]))
            else:
                # Ключ не имеет суффикса - используем как есть
                base_keys.add(key)

        return base_keys

    def safely_extract_indicators(self, definition: Any) -> list[str]:
        """
        Безопасно извлекает базовые ключи индикаторов из определения стратегии.

        Не падает на ошибках, возвращает то что удалось извлечь.
        Используется для частично некорректных определений.

        Args:
            definition: AST-дерево стратегии или None

        Returns:
            Отсортированный список базовых ключей индикаторов

        Example:
            >>> extractor = IndicatorExtractor()
            >>> definition = {"entry_conditions": {"type": "INDICATOR_VALUE", "key": "ema_timeperiod_12_value"}}
            >>> extractor.safely_extract_indicators(definition)
            ['ema_timeperiod_12']
        """
        if not definition or not isinstance(definition, dict):
            return []

        try:
            # Извлекаем полные ключи
            full_keys = self.extract_indicator_keys(definition)

            # Конвертируем в базовые ключи
            base_keys = self.extract_base_keys(full_keys)

            # Возвращаем отсортированный список
            return sorted(list(base_keys))

        except Exception:
            # Если что-то пошло не так - возвращаем пустой список
            return []
