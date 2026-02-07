# Changelog

All notable changes to the "Trade Forge" project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.11.0] - 2026-02-07

### Added
- **[Internal API]** Enhanced strategy validation during creation/update

### Changed
- **[CHANGELOG]** Translated to English
- **[README]** Translated to English

### Fixed
- **[Migrations]** Fixed ClickHouse migration deployment from scratch
- **[Infra]** Improved ClickHouse configuration
- **[Trading Engine]** **[Data Processor]** Bug fixes

## [0.10.0] - 2025-11-30

### Changed
- **[Trading Engine]** Complete service refactoring. Effectively a new service internally, but with the same external interface. LOC: 2k → 9.5k
- **[MOEX Collector]** Complete service refactoring. Full implementation of best practices, internal libraries, etc.
- **[Libs Core]** **[tradeforge_apiclient]** Complete library refactoring. Fixed bugs, reworked logging, documentation, etc.
- **[Libs Core]** **[tradeforge_kafka]** Integrated tradeforge_logger into the library
- **[Migrations]** Complete service overhaul. Now professional-grade, uses internal libraries, supports rollbacks
- **[Internal API]** Complete service refactoring. Supports internal libraries, fixed bugs, more readable. External interface unchanged
- **[Gateway API]** Complete service refactoring. Supports internal libraries, fixed bugs, more readable. External interface unchanged

### Fixed
- **[Libs Core]** **[tradeforge_kafka]** Fixed package name from previous version (smart_kafka) to new one (tradeforge_kafka)
- **[Trading Engine]** **[Data Processor]** Fixed minor error when working with ClickHouse
- **[Data Processor]** Fixed timezone error in online mode

### Removed
- **[Libs Core]** Removed legacy logger and perfprofiler libraries

## [0.9.0] - 2025-10-26

### Added
- **[Data Processor]** Distributed Lock Manager based on Redis to prevent race conditions during parallel batch indicator calculation tasks
- **[Data Processor]** Full integration of `tradeforge_logger` with unified logging format and automatic tracing
- **[Data Processor]** Graceful shutdown for ClickHouse clients with proper resource cleanup

### Changed
- **[Libs Core]** **[tradeforge_logger]** Added automatic basic configuration on first `get_logger()` call - no longer requires explicit `configure_logging()` call before importing modules
- **[Libs Core]** **[tradeforge_logger]** `version` field is no longer output to logs if set to "unknown"
- **[Data Processor]** 100% refactored and redesigned. Now this module uses best practices, validates many errors, works 100% asynchronously and has production-grade quality

### Fixed
- **[Libs Core]** **[tradeforge_logger]** Fixed RuntimeError when importing modules before calling `configure_logging()`
- **[Data Processor]** **[CRITICAL]** Fixed duplicate issue during parallel backtests through versioning:
  - **[ClickHouse Migration]** Added `version UInt64` column to `candles_indicators` table
  - **[ClickHouse Migration]** ENGINE changed to `ReplacingMergeTree(version)` for automatic deduplication
  - Each record receives a unique version (timestamp in microseconds)
  - In case of duplicates, ClickHouse automatically selects the record with MAX(version) when using FINAL

## [0.8.0] - 2025-10-20

### Added
- **[Libs Core]** `tradeforge_logger` library for unified structured logging with JSON format, automatic context (service_name, version, environment), Correlation ID for distributed tracing, automatic sensitive data masking and FastAPI/Kafka integration
- **[Libs Core]** `tradeforge_kafka` v2.0.0 library with full async/await support, automatic Pydantic message validation, retry logic with exponential backoff, Dead Letter Queue, Correlation ID for observability and graceful shutdown

### Changed
- **[CHANGELOG]** Significantly reduced (500 lines → 200 lines). Removed excessive details
- **[Breaking]** **[Libs Core]** Removed legacy `libs/core/database` library
- **[MOEX Collector]** Integrated `tradeforge_kafka` with batch sending support, automatic Pydantic validation and Correlation ID
- **[Trading Engine]** Integrated `tradeforge_kafka` with proper lifecycle management and error handling through `RetryableError`/`FatalError`
- **[Internal API]** Integrated `tradeforge_kafka` using `job_id` as correlation_id for distributed tracing
- **[Data Processor]** Integrated `tradeforge_kafka` v2.0.0 with support for parallel processing up to 10 tasks and thread-safe ClickHouse operations via ThreadLocal in `StorageManager`
- **[Trading Engine]** Full migration to `tradeforge_db`
- **[Data Processor]** Full migration to `tradeforge_db`
- **[MOEX Collector]** Full migration to `tradeforge_db`
- **[Gateway API]** Full migration to `tradeforge_db`
- **[Clickhouse Migrations]** `begin` column in all tables updated to `DateTime64(3, 'Europe/Moscow')`

## [0.7.0] - 2025-10-12

### Added
- **[Libs Core]** `tradeforge_db` library for PostgreSQL based on SQLAlchemy 2.0+ with async connection pool (asyncpg), Pydantic Settings for configuration and FastAPI dependency `get_db_session()`
- **[Trading Engine]** Support for real lot size (lot_size) in backtests with calculation of maximum number of lots based on available capital
- **[Trading Engine]** Ticker metadata caching with lazy initialization
- **[Trading Engine]** Position flip detection with logging
- **[Trading Engine]** Support for simulation parameters from DB (`initial_balance`, `commission_pct`, `position_size_pct`)
- **[Trading Engine]** Extended trade history metrics

### Changed
- **[Architecture]** SQLAlchemy models moved from `platform/migrator` to shared library `libs/core/tradeforge_db` - single source of truth for all services
- **[Trading Engine]** Migrated to structlog for structured JSON logging
- **[Trading Engine]** `leverage` parameter replaced with `position_size_pct` (50% = half capital, 100% = full capital, 200% = 2x leverage)
- **[API Schemas]** Increased maximum `position_size_pct` limit from 100% to 500% to support margin trading
- **[Trading Engine]** Complete migration to async PostgreSQL - `psycopg2` driver replaced with `asyncpg`
- **[Trading Engine]** Improved profit calculation semantics accounting for real number of shares and lot_size
- **[Trading Engine]** Optimized metrics calculation - removed duplication in `metrics_calculator.py`
- **[Internal API]** Completely rewritten database work using ORM style

### Fixed
- **[Trading Engine]** Fixed percentage profit calculation - `profit_pct` now correctly calculated from position value, not from single share price
- **[Trading Engine]** Fixed commission calculation - now calculated from actual position volume, not from total capital
- **[Trading Engine]** Eliminated confusion in `quantity` semantics - now unambiguously means number of shares (lots × lot_size)

## [0.6.0] - 2025-10-07

### Added
- **[Data Validation]** Lookback period validation system for indicators with two-stage verification: backtest period coverage + lookback candle availability
- **[RBAC]** Role and limit management system with `is_admin` field and `subscription_tier` (free, pro, enterprise)
- **[API]** Endpoint `GET /api/v1/profile/limits` for retrieving current user limits
- **[Security]** Administrative endpoints with `is_admin` check: token blocking, status verification
- **[Database]** Fields `is_admin` and `subscription_tier` in `auth.users` table
- **[Database]** Table `backtest_batches` for batch backtest operations
- **[Database]** Field `counts_towards_limit` in `backtest_jobs` table for correct task accounting in limits
- **[API]** Full support for batch backtest execution with unified validation and limit checking
- **[Data Validation]** Pre-execution validation of historical data availability before backtest launch with FAILED task creation without Kafka sending
- **[Rate Limiting]** Unified rate limit checking for single and batch backtests

### Changed
- **[API]** Backtest period validation by subscription tier moved from Internal API to Gateway API
- **[Database]** CRUD method `get_user_active_jobs_count()` only counts tasks with `counts_towards_limit = TRUE`
- **[Batch Processing]** Optimized batch backtest creation logic - data check with single SQL query
- **[Infrastructure]** Removed dependency on local Nexus PyPI repository - all dependencies installed directly from PyPI, simplified `libs/core/Dockerfile` structure
- **[Security]** Added protection against long passwords - automatic truncation to 72 bytes

### Fixed
- **[Security]** Fixed critical deadlock issue when CSRF and access tokens expire - removed CSRF check from `/auth/refresh` endpoint
- **[Security]** CSRF token now correctly updates in Redis during `/auth/refresh`
- **[Logging]** Fixed missing INFO logs in Gateway API via `logging.basicConfig()` configuration
- **[Critical]** Fixed timezone issue in ClickHouse queries - added conversion from timezone-aware to timezone-naive
- **[Critical]** Fixed candle count error in ClickHouse during data availability check
- **[Batch Processing]** Fixed `failed_count` display in batch backtest status
- **[Security]** Fixed `ValueError: password cannot be longer than 72 bytes` via automatic password truncation to 72 bytes

## [0.5.0] - 2025-09-25

### Added
- **[API]** Filtering by `strategy_id` in backtest list, `search` parameter for tickers, `market_code` filter
- **[API]** Endpoint `/metadata/tickers/popular` for popular tickers
- **[API]** Endpoints `/metadata/timeframes` and `/auth/logout`
- **[Authentication]** Token blacklist system in Redis for JWT invalidation
- **[API]** Extended authentication with session management: login, refresh (with Refresh Token Rotation), logout, session list, session deletion
- **[Security]** CSRF protection via `CSRFMiddleware`, security event logging in `auth.security_events`, Device Fingerprinting
- **[Core]** Middleware: `JWTSessionMiddleware` for session validation and `CSRFMiddleware` for CSRF protection
- **[Database]** Tables `auth.user_sessions`, `auth.token_blacklist`, `auth.security_events`
- **[API]** Dependencies `geoip2` and `user-agents` for geolocation and User-Agent analysis
- **[API]** Download of GeoIP MaxMind city database
- **[API]** Full sorting support for strategies (by name, dates, backtest count) and backtests (by 15+ metrics)
- **[Database]** Optimized indexes for sorting: composite and functional indexes on JSONB fields
- **[Schemas]** Enums for sorting parameters: `StrategySortBy`, `BacktestSortBy`, `SortDirection`

### Changed
- **[Database]** Tables `candles_base` and `candles_indicators` migrated to `ReplacingMergeTree` for automatic deduplication
- **[Schemas]** Schema `BacktestSummary` extended with all metrics from `BacktestMetrics`
- **[API]** Unified pagination limits to 200 elements across all endpoints
- **[API]** Removed unused custom indicators endpoint
- **[API Documentation]** Expanded ticker API documentation with search and filtering examples
- **[Authentication]** JWT verification migrated to async/await with token blacklist check
- **[Data Processor]** Improved deduplication: `ANTI LEFT JOIN` replaced with `NOT EXISTS`
- **[Trading Engine]** Improved data completeness check query with duplicate detection
- **[API]** CRUD functions updated to support dynamic sorting

### Fixed
- **[API]** Fixed missing metrics in backtest list, added fallback to `net_total_profit_pct` for `roi` field
- **[Internal API]** Fixed validation error in endpoint `/metadata/timeframes`
- **[API]** Fixed pagination limit mismatch between Gateway (1000) and Internal API (200)
- **[Critical]** Fixed SQL query error in ClickHouse that caused backtest crashes
- **[Data Processor]** Fixed duplicate filtering via partitioned check
- **[Trading Engine]** Fixed multi-component indicator handling (SuperTrend)
- **[Performance]** Optimized SQL queries for working with billions of records
- **[Data Quality]** Cleaned up ~20.5M duplicate candles and indicators
- **[API]** Eliminated N+1 query problem via `selectin load`
- **[Database Migration]** Fixed index migration for sorting - replaced `::` usage with `CAST()`
- **[API]** Fixed UnboundLocalError issue in CRUD function `get_user_backtest_jobs`

## [0.4.0] - 2025-09-14

### Added
- **[Libs Core]** Shared schema library `tradeforge_schemas` for unified API interfaces between Gateway and Internal API
- **[Internal API]** Automatic indicator validation and creation during strategy creation/update
- **[Internal API]** Table `users_indicators` for storing custom indicators with deduplication by base key
- **[API]** Strategy name uniqueness validation with edit support via `strategy_id` parameter
- **[API]** Strategy description save/retrieval functionality
- **[Database]** Field `is_deleted` for soft strategy deletion, columns `updated` and `description`
- **[Migrations]** Column `updated` in base TimeStamp model

### Changed
- **[Architecture]** Complete refactoring: Gateway simplified to proxy, all business logic centralized in Internal API
- **[API Validation]** Updated supported timeframes: 1d, 10min, 1h, 1w, 1m
- **[API]** Unified validation response formats according to RFC 7807
- **[API]** Improved HTTP status code logic for validation (200 for success, 422 for errors)
- **[API Localization]** Translated all user-facing error messages to Russian including Pydantic errors
- **[Internal API]** Validation endpoint accepts raw JSON and combines Pydantic errors with business logic
- **[Internal API]** Added validation for mandatory position entry conditions
- **[API Documentation]** Fixed Swagger schemas for strategy validation endpoints
- **[Internal API]** Modernized strategy logic with soft delete support
- **[Internal API]** CRUD operations updated to exclude deleted strategies from API responses
- **[Gateway API]** Significantly expanded Swagger documentation

### Fixed
- **[API]** Fixed validation HTTP status codes (200/422) and response formats
- **[API]** Fixed `description` parameter passing during strategy creation/update
- **[API]** Eliminated strategy name duplication issues during editing
- **[Internal API]** Fixed backtest info API endpoint
- **[Internal API]** Fixed indicator parameter serialization error in JSONB
- **[Internal API]** Eliminated API crash when requesting backtests for deleted strategies
- **[Gateway API]** Fixed field mapping `result` → `results` when retrieving backtest results
- **[Gateway API]** Improved security of error information transmission to frontend
- **[Architecture]** Eliminated duplicate Pydantic errors and "disappearing" name errors
- **[Migrations]** Fixed bbands indicator migration - changed key order

## [0.3.0] - 2025-09-08

### Added
- **[API]** External API service (`services/api/gateway`) for frontend interaction with Internal API

### Changed
- **[Migrations]** Minor user schema update

### Fixed
- **[Internal API]** Fixed startup file permissions

## [0.2.0] - 2025-09-07

### Added
- **[API]** Internal API service (`services/api/internal`) for strategy and backtest management
- **[Migrations]** Table `system_indicators` for indicator descriptions
- **[Indicators]** Universal indicator description structure
- **[Migrations]** Extended `backtest_jobs` table with new fields

### Changed
- **[Trading Engine]** Fixed reference to `users_indicators` table
- **[Infrastructure]** Updated container restart parameters
- **[README]** Major update reflecting current project status

## [0.1.0] - 2025-08-31

### Added
- **[Architecture]** Async microservice architecture based on Kafka with monorepo
- **[Infrastructure]** Containerized all dependencies: PostgreSQL 16, ClickHouse, Redis, Kafka (Confluent)
- **[Data Collection]** `moex-collector` service for collecting and publishing MOEX candles with automatic ticker registry synchronization
- **[Calculations]** `data-processor` service with Real-Time and Batch pipelines for technical indicator calculation
- **[Backtest]** `trading-engine` service with hybrid (vectorized/step-by-step) engine for strategy simulation
- **[Migrations]** `migrator` service for managing PostgreSQL (Alembic), ClickHouse schemas and Kafka topic creation
- **[Libs Core]** `python-base-core` library with utilities for API, Kafka, DB and logging

### Changed
- **[Data Collection]** Initial candle saving to ClickHouse moved from `data-processor` to `moex-collector`
- **[Data Collection]** Redis and ClickHouse synchronization logic moved to `Scheduler`

### Fixed
- **[Calculations]** Eliminated `FutureWarning` error when processing dates with timezones

[unreleased]: https://github.com/bodya18x/trade-forge/compare/v0.11.0...develop
[0.11.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.11.0
[0.10.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.10.0
[0.9.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.9.0
[0.8.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.8.0
[0.7.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.7.0
[0.6.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.6.0
[0.5.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.5.0
[0.4.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.4.0
[0.3.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.3.0
[0.2.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.2.0
[0.1.0]: https://github.com/bodya18x/trade-forge/releases/tag/v0.1.0
