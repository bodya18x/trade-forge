# Trade Forge

[![Version](https://img.shields.io/badge/version-0.11.0-blue.svg)](https://github.com/bodya18x/trade-forge/releases)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Async microservice platform for algorithmic trading strategy backtesting on Moscow Exchange (MOEX)**

> **Note:** This repository contains the complete backend infrastructure. The frontend is proprietary and not included in this public release.

---

## Overview

Trade Forge is a production-grade SaaS platform that provides traders with a **no-code strategy builder** to create, backtest, and (future) auto-trade algorithmic strategies on the Moscow Stock Exchange.

Instead of selling "signals", we provide professional tooling ("teach to fish") that enables traders without programming skills to rapidly test their trading hypotheses, trust the results, and make informed decisions.

## Architecture

Built on **async, event-driven microservice architecture** using a **monorepo** approach.

### Tech Stack

- **Core:** Python 3.13+, FastAPI, SQLAlchemy 2.0, Pydantic
- **Message Broker:** Apache Kafka (event-driven communication)
- **Databases:**
  - **PostgreSQL 16:** Application state, users, strategies, backtest jobs/results, reference data
  - **ClickHouse:** Time-series data (OHLCV candles, technical indicators)
  - **Redis:** Caching, real-time state management, rate limiting
- **Infrastructure:** Docker, Docker Compose

### Key Services

All services are located in `services/` directory and grouped by business domain:

| Service | Domain | Description |
|---------|--------|-------------|
| **moex_collector** | `market_data/` | Collects and stores market data (candles) from MOEX. Syncs tradable instruments registry |
| **data_processor** | `analytics/` | Computes technical indicators in Real-Time (live data) and Batch (historical) modes |
| **trading_engine** | `trading_core/` | Strategy execution engine. Orchestrates backtests, future real-time trading |
| **internal API** | `api/internal/` | Internal API service. Central business logic orchestrator |
| **gateway API** | `api/gateway/` | External API service. Secure public access to the platform |
| **migrator** | `platform/migrator/` | Database migrations (PostgreSQL, ClickHouse) and Kafka topic provisioning |

**Detailed documentation for each service is available in their respective README files.**

## Key Features

- ✅ **Async event-driven microservices** with Kafka-based communication
- ✅ **Real-time & batch technical indicator calculations** (RSI, MACD, Bollinger Bands, SuperTrend, etc.)
- ✅ **Hybrid backtesting engine** (vectorized + step-by-step simulation)
- ✅ **RBAC system** with subscription tiers (free, pro, enterprise)
- ✅ **Production-grade internal libraries**:
  - `tradeforge_db` - PostgreSQL with SQLAlchemy 2.0 async
  - `tradeforge_kafka` - Kafka client with retry logic, DLQ, correlation tracking
  - `tradeforge_logger` - Structured JSON logging with distributed tracing
  - `tradeforge_schemas` - Unified API schemas
- ✅ **Complete database migration system** with rollback support
- ✅ **Built-in deduplication** for high-volume time-series data
- ✅ **Comprehensive security**: JWT sessions, CSRF protection, token blacklist, device fingerprinting

## Development Highlights

- **Built from scratch** in 3 months (August - November 2025)
- **60,000+ lines of code** with production-grade architecture
- **Monorepo structure** for easier cross-service refactoring
- **Semantic versioning** with detailed [CHANGELOG](CHANGELOG.md)
- **GitFlow workflow** (main for stable releases, develop for active development)

## Quick Start (Development)

### Prerequisites
- Docker
- Docker Compose

### Setup

1. **Create Docker network:**
   ```bash
   docker network create shared_network
   ```

2. **Configure environment:**
   ```bash
   cp platform/.env.example platform/.env
   # Edit .env file with your configuration
   ```

3. **Start all services:**
   ```bash
   cd platform
   chmod +x compose
   ./compose start
   ```

4. **Stop services:**
   ```bash
   cd platform
   ./compose down
   ```

## Project Status

**Current version:** `0.11.0` (February 2026)

This project was developed as a **portfolio showcase** and **proof of concept** for production-grade microservice architecture in the fintech domain. While the backend is fully functional, it is **not actively maintained** for production use.

### What Works
- Complete data collection pipeline from MOEX
- Technical indicator calculations (20+ indicators)
- Strategy backtesting with realistic simulation
- API endpoints for strategy CRUD and backtest management
- User authentication and role-based access control
- Batch backtest execution with rate limiting

### Future Roadmap (Archived)
- Real-time trading execution
- Frontend web application
- Additional exchanges support (NASDAQ, NYSE)
- Machine learning integration for signal generation

## Architecture Decisions

Key architectural patterns and decisions are documented in service-specific READMEs. Some highlights:

- **Event Sourcing** for backtest job lifecycle
- **CQRS pattern** separating write (PostgreSQL) and read (ClickHouse) models
- **Distributed locks** (Redis) for preventing race conditions in batch processing
- **Graceful shutdown** handling for all async services
- **Correlation ID** tracking across microservices for distributed tracing
- **ReplacingMergeTree** for automatic time-series data deduplication

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Acknowledgments

Built with modern Python ecosystem:
- [FastAPI](https://fastapi.tiangolo.com/) - High-performance async web framework
- [SQLAlchemy 2.0](https://www.sqlalchemy.org/) - Database ORM
- [ClickHouse](https://clickhouse.com/) - Columnar database for analytics
- [Apache Kafka](https://kafka.apache.org/) - Distributed event streaming
- [Pydantic](https://pydantic.dev/) - Data validation

---

**Note:** This is a portfolio project showcasing backend microservice architecture for algorithmic trading. Not intended for production trading without significant additional testing and risk management.
