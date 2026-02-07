# --- Этап 1: Скачивание базы ---
FROM alpine:latest AS downloader

# Устанавливаем утилиты для скачивания и распаковки
RUN apk add --no-cache curl tar

# Аргумент для передачи лицензионного ключа
ARG MAXMIND_LICENSE_KEY

# Создаем папку и скачиваем базу GeoLite2 City
WORKDIR /geoip
RUN curl -L "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=${MAXMIND_LICENSE_KEY}&suffix=tar.gz" \
    -o GeoLite2-City.tar.gz

# Распаковываем архив и находим нужный файл
RUN tar -xzf GeoLite2-City.tar.gz && \
    mv $(find . -name 'GeoLite2-City.mmdb') /geoip/GeoLite2-City.mmdb

# --- Этап 2: Основная сборка приложения ---
FROM trade-forge-base:latest

ENV PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

# Устанавливаем зависимости сервиса
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код сервиса
COPY . .

# Копируем GeoIP базу из первого этапа в папку geoip внутри приложения
COPY --from=downloader /geoip/GeoLite2-City.mmdb ./geoip/GeoLite2-City.mmdb

RUN chmod +x load.sh

CMD ["./load.sh"]
