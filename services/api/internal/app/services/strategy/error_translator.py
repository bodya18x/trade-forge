"""
Переводчик ошибок Pydantic на русский язык.

Этот модуль предоставляет функционал для перевода стандартных
сообщений об ошибках Pydantic на русский язык для лучшего UX.
"""

from __future__ import annotations

import re


class ErrorTranslator:
    """
    Переводчик ошибок валидации Pydantic.

    Преобразует англоязычные сообщения об ошибках в русскоязычные
    для улучшения пользовательского опыта.
    """

    # Словарь переводов для наиболее частых ошибок Pydantic
    TRANSLATIONS = {
        # Типы данных
        "Input should be a valid dictionary": "Значение должно быть словарем",
        "Input should be a valid string": "Значение должно быть строкой",
        "Input should be a valid integer": "Значение должно быть целым числом",
        "Input should be a valid float": "Значение должно быть числом",
        "Input should be a valid boolean": "Значение должно быть булевым",
        "Input should be a valid list": "Значение должно быть списком",
        # Обязательные поля
        "Field required": "Обязательное поле",
        # Словари и объекты
        "Input should be a valid dictionary or object to extract fields from": "Значение должно быть словарем или объектом",
        "Extra inputs are not permitted": "Дополнительные поля не разрешены",
        # Строки
        "String should have at least 1 character": "Строка должна содержать минимум 1 символ",
        "String should have at most": "Строка не должна превышать",
        # Числа
        "Input should be greater than": "Значение должно быть больше",
        "Input should be less than": "Значение должно быть меньше",
        "Input should be greater than or equal to": "Значение должно быть больше или равно",
        "Input should be less than or equal to": "Значение должно быть меньше или равно",
        # UUID
        "Input should be a valid UUID": "Значение должно быть корректным UUID",
        # JSON
        "Invalid JSON": "Неверный формат JSON",
        # Enum
        "Input should be": "Значение должно быть одним из допустимых вариантов",
    }

    def translate(self, msg: str, error_type: str) -> str:
        """
        Переводит сообщение об ошибке Pydantic на русский язык.

        Args:
            msg: Оригинальное сообщение об ошибке на английском
            error_type: Тип ошибки Pydantic

        Returns:
            Переведенное сообщение на русском языке

        Example:
            >>> translator = ErrorTranslator()
            >>> translator.translate("Field required", "missing")
            'Обязательное поле'
        """
        # Пытаемся найти точное совпадение
        if msg in self.TRANSLATIONS:
            return self.TRANSLATIONS[msg]

        # Пытаемся найти частичное совпадение для динамических сообщений
        for english_pattern, russian_translation in self.TRANSLATIONS.items():
            if msg.startswith(english_pattern):
                # Для сообщений типа "String should have at most 255 characters"
                if "String should have at most" in msg:
                    match = re.search(r"at most (\d+)", msg)
                    if match:
                        limit = match.group(1)
                        return f"Строка не должна превышать {limit} символов"

                elif "Input should be greater than" in msg:
                    match = re.search(r"greater than (\d+(?:\.\d+)?)", msg)
                    if match:
                        limit = match.group(1)
                        return f"Значение должно быть больше {limit}"

                elif "Input should be less than" in msg:
                    match = re.search(r"less than (\d+(?:\.\d+)?)", msg)
                    if match:
                        limit = match.group(1)
                        return f"Значение должно быть меньше {limit}"

                return russian_translation

        # Если перевод не найден - возвращаем оригинальное сообщение
        return msg
