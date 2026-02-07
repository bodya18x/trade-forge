FROM trade-forge-base:latest

# Устанавливаем TA-Lib (специфично для data_processor)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        dpkg \
        build-essential \
    && wget https://github.com/TA-Lib/ta-lib/releases/download/v0.6.4/ta-lib_0.6.4_amd64.deb && \
    dpkg -i ta-lib_0.6.4_amd64.deb || true && \
    apt-get update && apt-get install -y -f && \
    rm ta-lib_0.6.4_amd64.deb && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости сервиса
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код сервиса
COPY . .

RUN chmod +x load.sh \
    wait-for-it.sh

CMD ["./load.sh"]