"""
Исключения для CRUD операций.

Определяет специфичные исключения для бизнес-логики CRUD операций.
"""

from __future__ import annotations


class DuplicateNameError(Exception):
    """Исключение для случаев дублирования имени сущности."""

    def __init__(self, entity_type: str, name: str):
        """
        Инициализирует исключение.

        Args:
            entity_type: Тип сущности (например, "Strategy")
            name: Имя, которое дублируется
        """
        self.entity_type = entity_type
        self.name = name
        super().__init__(f"{entity_type} with name '{name}' already exists")


class EntityNotFoundError(Exception):
    """Исключение для случаев когда сущность не найдена."""

    def __init__(self, entity_type: str, entity_id: str):
        """
        Инициализирует исключение.

        Args:
            entity_type: Тип сущности (например, "Strategy")
            entity_id: ID сущности
        """
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with id '{entity_id}' not found")
