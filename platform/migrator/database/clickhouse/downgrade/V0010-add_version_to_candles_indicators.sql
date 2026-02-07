-- ===================================================================
-- LEGACY DOWNGRADE: Полный откат схемы ClickHouse
-- ===================================================================
--
-- ВНИМАНИЕ: Этот downgrade удаляет ВСЮ схему ClickHouse trader!
--
-- Используется для legacy миграций (V0001-V0010).
-- Новые миграции должны иметь детальный downgrade.
--
-- ===================================================================

-- Удаляем все таблицы
DROP TABLE IF EXISTS trader.candles_indicators;
DROP TABLE IF EXISTS trader.candles_base;
DROP TABLE IF EXISTS trader.migrations;
