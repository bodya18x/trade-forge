# Trade Forge Migrator

## Что это?

Единый сервис для управления состоянием **всей инфраструктуры** платформы Trade Forge. Гарантирует, что схемы БД, топики Kafka и системные справочники соответствуют ожиданиям кода.

Запускается **один раз** при деплое/обновлении платформы.

## Типы миграций

1. **PostgreSQL** — основная БД (через Alembic + SQLAlchemy модели из `tradeforge_db`)
2. **ClickHouse** — аналитическая БД (кастомный мигратор, SQL файлы в `database/clickhouse/upgrade|downgrade`)
3. **Kafka** — создание и обновление топиков (конфигурация в `kafka_topics.yml`)
4. **Indicators** — синхронизация системных индикаторов с PostgreSQL (из `indicators/data/indicators.json`)

## Запуск

### Docker Compose
```bash
cd platform
docker-compose -f docker-compose.infra.yml up --build
# Миграции запустятся автоматически если MIGRATE=enabled в .env
```

### Локально (для разработки)
```bash
cd platform/migrator
pip install -r requirements.txt
pip install -e ../../libs/core
python main.py
```

## Создание новых миграций

### PostgreSQL
```bash
# 1. Измени модели в tradeforge_db
# 2. Сгенерируй миграцию
alembic revision --autogenerate -m "описание изменений"
# 3. Проверь и откорректируй созданный файл в database/postgresql/migrations/versions/
```

### ClickHouse
```bash
# 1. Создай upgrade файл: database/clickhouse/upgrade/V0011-название.sql
# 2. Создай downgrade файл: database/clickhouse/downgrade/V0011-название.sql (с тем же именем!)
# 3. Запусти миграции: python main.py
```

**Важно:** Upgrade применяется **ТОЛЬКО** если существует соответствующий downgrade файл. Это защита от потери данных.

### Kafka
Добавь топик в `kafka_topics.yml` и запусти миграции.

### Indicators
Добавь определение в `indicators/data/indicators.json` и запусти миграции.

## Архитектура

Все мигрирующие компоненты наследуются от `BaseMigrator` с единым интерфейсом:
- `health_check()` — проверка доступности
- `run()` — выполнение миграций
- `get_migration_status()` — текущий статус

Оркестратор (`main.py`) запускает миграции **последовательно** в порядке: PostgreSQL → ClickHouse → Kafka → Indicators. При провале любого шага процесс прерывается (fail-fast).

## Логирование

Структурированные JSON-логи через `tradeforge_logger`:
```json
{"timestamp": "...", "level": "info", "event": "postgresql_migrator.migration_started", "service": "migrator"}
```

## Переменные окружения

```bash
MIGRATE=enabled                    # Флаг включения миграций
POSTGRES_HOST=postgres             # PostgreSQL хост
CLICKHOUSE_HOST=clickhouse         # ClickHouse хост
KAFKA_BOOTSTRAP_SERVERS=kafka:9092 # Kafka серверы
```
