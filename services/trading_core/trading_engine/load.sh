#!/bin/bash
./wait-for-it.sh -t 30 ${KAFKA_BOOTSTRAP_SERVERS}

echo 'Trading Engine starting!'

# Запуск в зависимости от RUN_ARG (backtest или realtime)
if [ "$RUN_ARG" = "realtime" ]; then
    echo 'Starting in REALTIME mode...'
    python application.py consume-rt
else
    echo 'Starting in BACKTEST mode...'
    python application.py consume-backtest
fi
