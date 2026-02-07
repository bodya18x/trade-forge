from __future__ import annotations

from enum import Enum


class HTTPMethod(Enum):
    """Перечисление всех доступных HTTP-методов для API-клиента.

    Содержит основные методы, используемые для отправки запросов.
    Может быть расширен при необходимости.
    """

    GET = "get"
    POST = "post"
    PUT = "put"
    DELETE = "delete"
    PATCH = "patch"

    @classmethod
    def list_methods(cls) -> list[str]:
        """Возвращает список всех поддерживаемых HTTP-методов.

        Returns:
            list[str]: Список строковых значений HTTP-методов.
        """
        return [method.value for method in cls]
