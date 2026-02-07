# Trade Forge Database Library

Библиотека для работы с PostgreSQL в проекте Trade Forge. Предоставляет SQLAlchemy 2.0 модели, менеджер соединений и FastAPI dependencies для всех микросервисов.

## 📦 Возможности

- ✅ **SQLAlchemy 2.0+ модели** для всех таблиц PostgreSQL
- ✅ **Асинхронный драйвер** asyncpg для высокой производительности
- ✅ **Pydantic Settings** для конфигурации подключения
- ✅ **DatabaseManager** с управлением пулом соединений
- ✅ **FastAPI Dependency Injection** для эндпоинтов

## 🔧 Конфигурация

Библиотека использует переменные окружения для настройки подключения:

```env
# Обязательные параметры
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=trader
POSTGRES_USER=admin
POSTGRES_PASSWORD=strong_password

# Опциональные параметры (со значениями по умолчанию)
POSTGRES_POOL_SIZE=10
POSTGRES_MAX_OVERFLOW=20
POSTGRES_POOL_PRE_PING=true
POSTGRES_ECHO=false
```

## 🎯 Best Practices

### 1. Инициализация при старте приложения

```python
# В main.py или app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from tradeforge_db import init_db, close_db, DatabaseSettings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = DatabaseSettings()
    init_db(settings)
    yield
    # Shutdown
    await close_db()

app = FastAPI(lifespan=lifespan)
```

### 2. SQLAlchemy 2.0 синтаксис

```python
# ✅ ПРАВИЛЬНО
result = await db.execute(select(Users).where(Users.id == user_id))
user = result.scalar_one_or_none()

# ❌ НЕПРАВИЛЬНО (legacy)
user = db.query(Users).filter(Users.id == user_id).first()
```

### 3. Транзакции

```python
# Автоматический commit/rollback через context manager
async with db_manager.session() as session:
    user = Users(email="test@example.com")
    session.add(user)
    # commit происходит автоматически при выходе

# Явный rollback при ошибке
async with db_manager.session() as session:
    try:
        # ... операции ...
        pass
    except Exception:
        # rollback происходит автоматически
        raise
```

## 🔗 Связь с миграциями

Модели из этой библиотеки используются в `platform/migrator` для генерации миграций:

```python
# platform/migrator/database/postgresql/migrations/env.py
from tradeforge_db.models import Base  # Импорт из библиотеки!

target_metadata = Base.metadata
```

## 🚧 Будущие улучшения

- [ ] Repository pattern для сложных запросов
- [ ] Утилиты для bulk операций
- [ ] Метрики производительности
