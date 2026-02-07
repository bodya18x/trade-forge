FROM trade-forge-base:latest

# Устанавливаем специфичные для migrator зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    liblz4-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости сервиса
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код сервиса
COPY . .

RUN chmod +x load.sh \
    wait-for-it.sh

CMD ["./load.sh"]
