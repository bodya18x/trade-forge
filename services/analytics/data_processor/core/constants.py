"""
Constants for data_processor service.

Все константы сервиса в одном месте для легкой настройки и поддержки.
"""

from __future__ import annotations

# Redis Cache
DEFAULT_CONTEXT_CANDLES_SIZE = 500
REDIS_CONTEXT_KEY_PREFIX = "candles_context"

# Versioning для ReplacingMergeTree
MICROSECONDS_MULTIPLIER = 1_000_000

# Distributed Locks
DEFAULT_LOCK_TIMEOUT_SECONDS = 60
DEFAULT_LOCK_TTL_SECONDS = 300
DEFAULT_LOCK_POLL_INTERVAL_SECONDS = 0.1

# ClickHouse
CLICKHOUSE_CANDLES_INDICATORS_TABLE = "trader.candles_indicators"

# Data Transformation
# Разделитель для indicator_key и value_key при трансформации в long format
INDICATOR_VALUE_SEPARATOR = "__SEP__"
