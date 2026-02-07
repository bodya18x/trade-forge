# -*- coding: utf-8 -*-
"""Установка."""
from setuptools import find_packages, setup

# Основные зависимости core библиотеки
install_requires = [
    "pika==1.3.2",
    "httpx==0.27.2",
    "memory_profiler==0.61.0",
    "setuptools==75.5.0",
    "twine==5.1.1",
    "sqlalchemy==2.0.44",
    "confluent-kafka==2.12.0",
    "psycopg2-binary==2.9.10",
    "asyncpg==0.30.0",  # Асинхронный драйвер для PostgreSQL
    "pydantic==2.9.2",
    "pydantic-settings==2.11.0",  # Для DatabaseSettings
    "email-validator==2.3.0",
    "structlog==25.4.0",
]

setup(
    name="python-base-core",
    version="1.0.0",
    packages=find_packages(exclude=["tests"]),
    install_requires=install_requires,
)
