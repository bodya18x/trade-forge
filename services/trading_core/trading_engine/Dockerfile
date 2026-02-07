FROM trade-forge-base:latest

# Устанавливаем зависимости сервиса
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код сервиса
COPY . .

RUN chmod +x load.sh \
    wait-for-it.sh

CMD ["./load.sh"]