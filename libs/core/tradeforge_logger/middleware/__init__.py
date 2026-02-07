# -*- coding: utf-8 -*-
"""Middleware для интеграции с веб-фреймворками и брокерами сообщений."""

from __future__ import annotations

from .fastapi import LoggingMiddleware, RequestContextMiddleware
from .kafka import KafkaContextMiddleware

__all__ = [
    "LoggingMiddleware",
    "RequestContextMiddleware",
    "KafkaContextMiddleware",
]
