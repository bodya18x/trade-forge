"""
Модуль для расширенного device fingerprinting с GeoIP и детекцией устройств.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
from typing import Optional

import geoip2.database
import geoip2.errors
from tradeforge_logger import get_logger
from user_agents import parse

from app.settings import settings

log = get_logger(__name__)


class DeviceFingerprintEnricher:
    """
    Класс для обогащения device fingerprint дополнительными данными:
    - GeoIP информация (страна, город, ISP)
    - Детальный парсинг User-Agent (браузер, ОС, устройство)
    """

    def __init__(self):
        """Инициализация обогащателя fingerprint."""
        self.geoip_reader = None
        self._init_geoip_database()

    def _init_geoip_database(self):
        """
        Инициализирует GeoIP базу данных.

        В продакшене должна быть загружена MaxMind GeoLite2 база.
        Для MVP используем заглушки для localhost/локальных IP.
        """
        try:
            # Путь к GeoIP базе данных (в продакшене должен быть настроен)
            geoip_db_path = settings.GEOIP_DATABASE_PATH

            if geoip_db_path and Path(geoip_db_path).exists():
                self.geoip_reader = geoip2.database.Reader(geoip_db_path)
                log.info("geoip.database.initialized", path=geoip_db_path)
            else:
                log.warning(
                    "geoip.database.not.found",
                    path=geoip_db_path,
                    note="Using mock data for development",
                )
        except Exception as e:
            log.error("geoip.database.initialization.failed", error=str(e))

    async def enrich_fingerprint(
        self, client_ip: str, user_agent: str, base_fingerprint: dict
    ) -> dict:
        """
        Обогащает базовый device fingerprint дополнительными данными.

        Args:
            client_ip: IP адрес клиента
            user_agent: User-Agent строка
            base_fingerprint: Базовый fingerprint от клиента

        Returns:
            Обогащенный fingerprint с дополнительными полями
        """
        enriched = base_fingerprint.copy()

        # Добавляем GeoIP информацию
        geo_info = await self._get_geo_info(client_ip)
        if geo_info:
            enriched["geo"] = geo_info

        # Добавляем детальную информацию о User-Agent
        ua_info = self._parse_user_agent(user_agent)
        if ua_info:
            enriched["parsed_user_agent"] = ua_info

        # Добавляем метаданные обогащения
        from datetime import datetime, timezone

        enriched["enrichment_meta"] = {
            "client_ip": client_ip,
            "ip_type": self._classify_ip_type(client_ip),
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        }

        return enriched

    async def _get_geo_info(self, ip_address: str) -> Optional[dict]:
        """
        Получает географическую информацию по IP адресу.

        Args:
            ip_address: IP адрес для анализа

        Returns:
            Словарь с географическими данными или None
        """
        try:
            # Проверяем, является ли IP локальным/приватным
            ip_obj = ipaddress.ip_address(ip_address)
            if ip_obj.is_private or ip_obj.is_loopback:
                return self._get_mock_geo_info_for_local_ip()

            # Если есть GeoIP база данных, используем её
            if self.geoip_reader:
                try:
                    response = self.geoip_reader.city(ip_address)
                    return {
                        "country_code": response.country.iso_code,
                        "country_name": response.country.name,
                        "city": response.city.name,
                        "region": response.subdivisions.most_specific.name,
                        "timezone": str(response.location.time_zone),
                        "latitude": (
                            float(response.location.latitude)
                            if response.location.latitude
                            else None
                        ),
                        "longitude": (
                            float(response.location.longitude)
                            if response.location.longitude
                            else None
                        ),
                        "accuracy_radius": response.location.accuracy_radius,
                        "source": "geoip2",
                    }
                except geoip2.errors.AddressNotFoundError:
                    log.debug("geoip.address.not.found", ip=ip_address)
                    return None
                except Exception as e:
                    log.error(
                        "geoip.lookup.failed", ip=ip_address, error=str(e)
                    )
                    return None

            # Если GeoIP база недоступна, возвращаем заглушку для MVP
            return self._get_mock_geo_info_for_public_ip()

        except Exception as e:
            log.error("geoip.info.get.failed", ip=ip_address, error=str(e))
            return None

    def _get_mock_geo_info_for_local_ip(self) -> dict:
        """Возвращает заглушку для локальных IP адресов."""
        return {
            "country_code": "RU",
            "country_name": "Russia",
            "city": "Moscow",
            "region": "Moscow",
            "timezone": "Europe/Moscow",
            "latitude": 55.7558,
            "longitude": 37.6176,
            "accuracy_radius": 1000,
            "source": "mock_local",
        }

    def _get_mock_geo_info_for_public_ip(self) -> dict:
        """Возвращает заглушку для публичных IP адресов в MVP."""
        return {
            "country_code": "RU",
            "country_name": "Russia",
            "city": "Saint Petersburg",
            "region": "Saint Petersburg",
            "timezone": "Europe/Moscow",
            "latitude": 59.9311,
            "longitude": 30.3609,
            "accuracy_radius": 50,
            "source": "mock_public",
        }

    def _parse_user_agent(self, user_agent: str) -> Optional[dict]:
        """
        Парсит User-Agent строку для извлечения детальной информации.

        Args:
            user_agent: User-Agent строка

        Returns:
            Словарь с распарсенной информацией об устройстве
        """
        try:
            ua = parse(user_agent)

            return {
                # Браузер
                "browser": {
                    "family": ua.browser.family,
                    "version": ua.browser.version_string,
                    "version_major": (
                        ua.browser.version[0] if ua.browser.version else None
                    ),
                },
                # Операционная система
                "os": {
                    "family": ua.os.family,
                    "version": ua.os.version_string,
                    "version_major": (
                        ua.os.version[0] if ua.os.version else None
                    ),
                },
                # Устройство
                "device": {
                    "family": ua.device.family,
                    "brand": ua.device.brand,
                    "model": ua.device.model,
                    "is_mobile": ua.is_mobile,
                    "is_tablet": ua.is_tablet,
                    "is_pc": ua.is_pc,
                    "is_bot": ua.is_bot,
                },
                # Дополнительные флаги
                "flags": {
                    "is_mobile": ua.is_mobile,
                    "is_tablet": ua.is_tablet,
                    "is_pc": ua.is_pc,
                    "is_bot": ua.is_bot,
                    "is_email_client": ua.is_email_client,
                },
            }

        except Exception as e:
            log.error(
                "user.agent.parse.failed",
                user_agent=user_agent,
                error=str(e),
            )
            return None

    def _classify_ip_type(self, ip_address: str) -> str:
        """
        Классифицирует тип IP адреса.

        Args:
            ip_address: IP адрес для классификации

        Returns:
            Тип IP адреса (private, loopback, public, invalid)
        """
        try:
            ip_obj = ipaddress.ip_address(ip_address)

            if ip_obj.is_loopback:
                return "loopback"
            elif ip_obj.is_private:
                return "private"
            elif ip_obj.is_global:
                return "public"
            else:
                return "special"

        except ValueError:
            return "invalid"

    def create_security_fingerprint_hash(
        self, enriched_fingerprint: dict
    ) -> str:
        """
        Создает хеш от обогащенного fingerprint для целей безопасности.

        Использует стабильные поля, которые не изменяются при каждом запросе.

        Args:
            enriched_fingerprint: Обогащенный fingerprint

        Returns:
            SHA-256 хеш от ключевых полей fingerprint
        """
        # Выбираем стабильные поля для хеширования
        stable_fields = {
            "screen_resolution": enriched_fingerprint.get("screen_resolution"),
            "timezone": enriched_fingerprint.get("timezone"),
            "language": enriched_fingerprint.get("language"),
            "browser_family": enriched_fingerprint.get("parsed_user_agent", {})
            .get("browser", {})
            .get("family"),
            "os_family": enriched_fingerprint.get("parsed_user_agent", {})
            .get("os", {})
            .get("family"),
            "device_type": (
                "mobile"
                if enriched_fingerprint.get("parsed_user_agent", {})
                .get("flags", {})
                .get("is_mobile")
                else "desktop"
            ),
            "country_code": enriched_fingerprint.get("geo", {}).get(
                "country_code"
            ),
        }

        # Убираем None значения и сортируем для стабильности
        stable_fields = {
            k: v for k, v in stable_fields.items() if v is not None
        }
        fingerprint_string = json.dumps(stable_fields, sort_keys=True)

        return hashlib.sha256(fingerprint_string.encode()).hexdigest()

    def __del__(self):
        """Закрывает GeoIP базу данных при удалении объекта."""
        if self.geoip_reader:
            try:
                self.geoip_reader.close()
            except Exception:
                pass  # Игнорируем ошибки при закрытии


# Глобальный экземпляр для использования в приложении
device_fingerprint_enricher = DeviceFingerprintEnricher()
