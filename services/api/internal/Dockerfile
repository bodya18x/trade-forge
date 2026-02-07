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

RUN chmod +x load.sh

CMD ["./load.sh"]
