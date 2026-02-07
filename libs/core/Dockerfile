FROM python:3.13-slim

WORKDIR /tmp/core

# Устанавливаем базовые системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Обновляем pip
RUN pip install --upgrade pip

# Копируем и устанавливаем core библиотеку
COPY . .
RUN pip install . -U

# Очищаем временные файлы
RUN rm -rf /tmp/core

# Устанавливаем рабочую директорию для сервисов
WORKDIR /usr/src/app

# Base image готов для использования сервисами
CMD ["bash"]
