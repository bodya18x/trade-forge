#!/bin/bash
set -e -o pipefail

echo "==========================================="
echo "Trade Forge Migration Service"
echo "==========================================="
echo ""

# Health checks для критических сервисов
echo "⏳ Waiting for infrastructure services..."

./wait-for-it.sh -t 30 ${POSTGRES_HOST}:${POSTGRES_PORT}
echo "✅ PostgreSQL is ready"

./wait-for-it.sh -t 30 ${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}
echo "✅ ClickHouse is ready"

./wait-for-it.sh -t 60 ${KAFKA_BOOTSTRAP_SERVERS}
echo "✅ Kafka is ready"

echo ""
echo "-------------------------------------------"

# Проверяем флаг MIGRATE
if [ "$MIGRATE" = "enabled" ] ; then
  echo "🚀 Starting Trade Forge Migrations (UPGRADE)..."
  echo ""

  # Запускаем alembic миграции в PostgreSQL
  alembic upgrade head

  # Запускаем главный оркестратор миграций
  python main.py
  EXIT_CODE=$?

  echo ""
  echo "-------------------------------------------"

  if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All migrations completed successfully!"
    echo "==========================================="
    exit 0
  else
    echo "❌ Migrations failed with exit code $EXIT_CODE"
    echo "==========================================="
    exit $EXIT_CODE
  fi

elif [ "$MIGRATE" = "downgrade-clickhouse" ] ; then
  # Откатываем Clickhouse миграцию последнюю
  python main.py --rollback
elif [ "$MIGRATE" = "downgrade-alembic" ] ; then
  # Откатываем Alembic миграции
  alembic downgrade -1
else
  echo "❌ ERROR: MIGRATE environment variable must be set to 'enabled' or 'downgrade-*'"
  echo "   Current value: '$MIGRATE'"
  echo "==========================================="
  exit 1
fi
