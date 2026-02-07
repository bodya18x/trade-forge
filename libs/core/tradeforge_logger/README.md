# Trade Forge Logger

Production-ready библиотека для унифицированного структурированного логирования в микросервисной архитектуре Trade Forge.

## Основные возможности

- ✅ **Структурированное логирование** - все логи в JSON формате для легкого парсинга
- ✅ **Автоматический контекст** - service_name, version, environment, correlation_id
- ✅ **Sanitization** - автоматическая очистка чувствительных данных (пароли, токены)
- ✅ **FastAPI интеграция** - middleware для автоматического логирования HTTP запросов
- ✅ **Async-safe** - использование ContextVars для безопасности в асинхронном коде
- ✅ **Type-safe** - 100% аннотации типов

## Быстрый старт

### 1. Инициализация в main.py

```python
from tradeforge_logger import configure_logging, get_logger

# Конфигурируем логирование при старте приложения
configure_logging(
    service_name="order-service",
    version="1.2.3",
    environment="production",  # или "development", "staging"
    log_level="INFO",
    enable_json=True,  # JSON для production, False для development
)

logger = get_logger(__name__)
logger.info("service.started", port=8000)
```

### 2. Использование в модулях

```python
from tradeforge_logger import get_logger

logger = get_logger(__name__)

# Простое логирование событий
logger.info("order.created", order_id="ORD-123", user_id="user_789", amount=100.50)

# Логирование ошибок
try:
    process_payment(order)
except PaymentError as e:
    logger.error(
        "payment.failed",
        order_id=order.id,
        error_type=type(e).__name__,
        exc_info=True  # добавит полный стек-трейс
    )
```

### 3. FastAPI интеграция

```python
from fastapi import FastAPI
from tradeforge_logger import configure_logging, get_logger
from tradeforge_logger.middleware import RequestContextMiddleware, LoggingMiddleware

configure_logging(service_name="api-service", environment="production")

app = FastAPI()

# ВАЖНО: RequestContextMiddleware должен быть ПЕРВЫМ
app.add_middleware(RequestContextMiddleware)
app.add_middleware(LoggingMiddleware)

logger = get_logger(__name__)

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    # request_id и correlation_id уже в контексте автоматически
    logger.info("fetching.order", order_id=order_id)
    return {"order_id": order_id}
```

## Формат логов

### Production (JSON)

```json
{
  "timestamp": "2025-10-19T14:23:45.123456Z",
  "level": "info",
  "event": "order.created",
  "logger": "order_service.handlers.orders",
  "service": "order-service",
  "version": "1.2.3",
  "environment": "production",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "req_7f8b9c123",
  "order_id": "ORD-123",
  "amount": 100.50
}
```

### Development (Console)

```
2025-10-19 14:23:45.123 [INFO    ] order.created
    order_id: ORD-123
    amount: 100.50
    correlation_id: 550e8400-e29b-41d4-a716-446655440000
```

## Управление контекстом

```python
from tradeforge_logger import bind_context, get_logger

logger = get_logger(__name__)

# Временный контекст
with bind_context(transaction_id="tx_123", user_id="user_456"):
    logger.info("transaction.started")  # содержит transaction_id и user_id
    logger.info("transaction.completed")  # также содержит контекст
```

## Конфигурация

### Через environment переменные

```bash
export TRADEFORGE_LOG_SERVICE_NAME=order-service
export TRADEFORGE_LOG_VERSION=1.2.3
export TRADEFORGE_LOG_ENVIRONMENT=production
export TRADEFORGE_LOG_LOG_LEVEL=INFO
export TRADEFORGE_LOG_ENABLE_JSON=true
```

```python
from tradeforge_logger import LoggerConfig, configure_logging

# Автоматически загрузит из env переменных
config = LoggerConfig(service_name="order-service")
configure_logging(config)
```

## Best Practices

### ✅ Что логировать

```python
# Бизнес-события
logger.info("order.created", order_id=order.id)

# Ошибки
logger.error("order.processing.failed", order_id=order.id, exc_info=True)

# Performance metrics
logger.info("database.query.slow", query_time_ms=1500)
```

### ❌ Чего НЕ делать

```python
# ❌ Не использовать f-strings для логов
logger.info(f"Order {order_id} created")  # NO!

# Вместо этого:
logger.info("order.created", order_id=order_id)  # YES!
```

### Naming Convention

```python
# Формат: <объект>.<действие>

# ✅ Хорошо
"order.created"
"payment.processed"
"user.authenticated"

# ❌ Плохо
"order creation"
```

## Sanitization

Библиотека автоматически маскирует чувствительные данные:

```python
logger.info("user.created", username="john", password="secret123")

# В логе:
# {"event": "user.created", "username": "john", "password": "[REDACTED]"}
```

Список полей по умолчанию: password, token, secret, api_key, authorization, credit_card, cvv, ssn, passport, private_key

## Лицензия

Internal library for Trade Forge project.
