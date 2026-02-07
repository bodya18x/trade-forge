-- Скрипт создаёт базу (если нету) и таблицу "migrations"
-- после чего вставляет информацию о применённой миграции.
CREATE DATABASE IF NOT EXISTS trader;

-- Переходим в эту БД (это удобно, чтобы не писать trader. перед каждой таблицей)
USE trader;

CREATE TABLE IF NOT EXISTS migrations
(
    migration_name String,
    applied_at     DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY migration_name;
