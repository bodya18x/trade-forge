#!/bin/bash
# ------------------------------------------------------------------------------
# Description: Скрипт для запуска режима "consume" Python-приложения, который
#              осуществляет сбор свечей из Kafka.
# ------------------------------------------------------------------------------
set -e

echo "Candles collector starting!"

python application.py consume

echo "Consumer finished execution."
