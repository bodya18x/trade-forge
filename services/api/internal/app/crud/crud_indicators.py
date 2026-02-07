"""
CRUD операции для работы с пользовательскими индикаторами.

Этот модуль содержит функции для создания и проверки экземпляров индикаторов,
используемых в стратегиях пользователей.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_db import UsersIndicators
from tradeforge_logger import get_logger

log = get_logger(__name__)


async def ensure_user_indicator_exists(
    db: AsyncSession,
    indicator_key: str,
    name: str,
    params: dict,
    is_hot: bool = False,
) -> None:
    """
    Проверяет существование индикатора в users_indicators.

    Если индикатор не найден - создает его.

    Args:
        db: Асинхронная сессия базы данных
        indicator_key: Полный ключ индикатора (например, "ema_timeperiod_12_value")
        name: Базовое имя индикатора (например, "ema")
        params: Параметры индикатора (например, {"timeperiod": 12})
        is_hot: Флаг для RT калькулятора (нужно ли считать в real-time)
    """
    # Проверяем существование индикатора
    stmt = select(UsersIndicators.id).where(
        UsersIndicators.indicator_key == indicator_key
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if not existing:
        # Создаем новый индикатор
        indicator = UsersIndicators(
            indicator_key=indicator_key,
            name=name,
            params=params,
            is_hot=is_hot,
        )
        db.add(indicator)
        await db.flush()


async def ensure_multiple_user_indicators_exist(
    db: AsyncSession, indicators: list[dict]
) -> None:
    """
    Массово проверяет и создает необходимые индикаторы.

    Args:
        db: Асинхронная сессия базы данных
        indicators: Список словарей с ключами indicator_key, name, params, is_hot
    """
    if not indicators:
        return

    # Получаем все существующие ключи за один запрос
    indicator_keys = [ind["indicator_key"] for ind in indicators]
    stmt = select(UsersIndicators.indicator_key).where(
        UsersIndicators.indicator_key.in_(indicator_keys)
    )
    result = await db.execute(stmt)
    existing_keys = set(result.scalars().all())

    # Определяем какие индикаторы нужно создать
    missing_indicators = [
        ind for ind in indicators if ind["indicator_key"] not in existing_keys
    ]

    if missing_indicators:
        # Массово создаем недостающие индикаторы через bulk insert
        stmt = insert(UsersIndicators).values(
            [
                {
                    "indicator_key": ind["indicator_key"],
                    "name": ind["name"],
                    "params": ind["params"],
                    "is_hot": ind["is_hot"],
                }
                for ind in missing_indicators
            ]
        )
        await db.execute(stmt)
        await db.flush()


def parse_indicator_from_key(indicator_key: str) -> dict:
    """
    Парсит полный ключ индикатора и извлекает базовое имя и параметры.

    Автоматически нормализует параметры: если integer параметр содержит .0,
    он будет преобразован в целое число на основе схемы индикатора.

    Args:
        indicator_key: Полный ключ типа "ema_timeperiod_12_value"
                      или "supertrend_length_10_multiplier_3.0_direction"

    Returns:
        Словарь с ключами:
            - name: Базовое имя индикатора
            - params: Словарь параметров индикатора (нормализованных)
    """
    # Lazy import для избежания циклической зависимости
    from app.services.strategy.indicator_key_validator import (
        IndicatorKeyValidator,
    )

    # Нормализуем ключ перед парсингом (убираем .0 из integer параметров)
    validator = IndicatorKeyValidator()
    normalized_key = validator.normalize_indicator_key(indicator_key)

    # Удаляем суффикс значения
    value_suffixes = [
        "value",
        "direction",
        "long",
        "short",
        "macd",
        "signal",
        "hist",
        "k",
        "d",
    ]

    parts = normalized_key.split("_")
    if len(parts) > 1 and parts[-1] in value_suffixes:
        base_key = "_".join(parts[:-1])
    else:
        base_key = normalized_key

    # Парсим параметры из базового ключа
    parts = base_key.split("_")

    # Если менее 3 частей, то это простое имя без параметров
    if len(parts) < 3:
        return {"name": base_key, "params": {}}

    name = parts[0]
    params = {}

    # Простая логика парсинга параметров
    i = 1
    while i < len(parts):
        param_name = parts[i]
        if i + 1 < len(parts):
            param_value = parts[i + 1]
            # Пытаемся преобразовать в число
            try:
                if "." in param_value:
                    params[param_name] = float(param_value)
                else:
                    params[param_name] = int(param_value)
                i += 2
            except ValueError:
                # Если не удалось преобразовать в число, возможно это составное имя
                return {"name": base_key, "params": {}}
        else:
            break

    # Если не смогли распарсить ни одного параметра, возвращаем весь ключ как имя
    if not params:
        return {"name": base_key, "params": {}}

    return {"name": name, "params": params}
