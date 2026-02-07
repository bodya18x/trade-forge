#!/bin/bash
# ------------------------------------------------------------------------------
# Описание: Запуск планировщика для создания задач на сбор свечей.
#
# Вызывается из cron с таймфреймом и опциональным кодом рынка.
# Создает задачи для всех активных тикеров и отправляет их в Kafka.
#
# Использование:
#   ./schedule_candles.sh <timeframe> [market_code] [--sync-redis]
#
# Примеры:
#   ./schedule_candles.sh 1h
#   ./schedule_candles.sh 1h moex_stock
#   ./schedule_candles.sh 1h moex_stock --sync-redis
# ------------------------------------------------------------------------------
set -euo pipefail

# Обновляем PATH для корректного поиска python.
export PATH=/usr/local/bin:$PATH

# Загружаем ENV из Docker (PID 1) в текущую сессию
export $(cat /proc/1/environ | tr '\0' '\n')

TIMEFRAME="${1:-}"
MARKET_CODE="${2:-moex_stock}"
SYNC_REDIS="${3:-}"

# Если второй аргумент --sync-redis, используем код рынка по умолчанию
if [ "$MARKET_CODE" == "--sync-redis" ]; then
    SYNC_REDIS="$MARKET_CODE"
    MARKET_CODE="moex_stock"
fi

if [ -z "$TIMEFRAME" ]; then
    echo "ОШИБКА: Требуется указать таймфрейм"
    echo "Использование: $0 <timeframe> [market_code] [--sync-redis]"
    exit 1
fi

echo "=========================================="
echo "MOEX Collector Scheduler"
echo "=========================================="
echo "Timeframe: $TIMEFRAME"
echo "Market: $MARKET_CODE"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# Формируем команду с таймфреймом и кодом рынка
CMD="python /usr/src/app/application.py schedule --collection-type candles -t $TIMEFRAME -m $MARKET_CODE"

# Добавляем sync-redis если передан
if [ "$SYNC_REDIS" == "--sync-redis" ]; then
    CMD="$CMD --sync-redis"
    echo "Синхронизация Redis: ВКЛЮЧЕНА"
else
    echo "Синхронизация Redis: ВЫКЛЮЧЕНА"
fi

echo "=========================================="

$CMD

EXIT_CODE=$?

echo "=========================================="
echo "Exit code: $EXIT_CODE"
echo "=========================================="

exit $EXIT_CODE
