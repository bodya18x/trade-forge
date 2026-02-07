# tradeforge_kafka

Асинхронная библиотека для работы с Apache Kafka на основе `confluent-kafka`.

## Ключевые возможности

✅ **100% async/await** - Полностью асинхронный API  
✅ **Pydantic валидация** - Автоматическая валидация сообщений  
✅ **Type safety** - Generic типы для безопасности  
✅ **Retry logic** - Exponential backoff  
✅ **Dead Letter Queue** - Автоматическая отправка в DLQ  
✅ **Observability** - Correlation ID, tradeforge_logger, метрики  
✅ **Graceful shutdown** - Context managers  
✅ **Production-ready** - Используется в Trade Forge

## Структура

```
tradeforge_kafka/
├── __init__.py              # Главный экспорт
├── datatypes.py             # Pydantic схемы (KafkaMessage, RecordMetadata)
├── config.py                # Конфигурация (ConsumerConfig, ProducerConfig)
├── metrics.py               # Метрики (ConsumerMetrics, ProducerMetrics)
├── exceptions.py            # Исключения
├── consumer/
│   ├── base.py             # AsyncKafkaConsumer
│   └── decorators.py       # @retry, @timeout, @circuit_breaker
├── producer/
│   └── base.py             # AsyncKafkaProducer
└── admin/
    ├── client.py           # KafkaAdmin
    └── async_client.py     # AsyncKafkaAdmin
```

## Быстрый старт

См. примеры в каждом модуле.

## Архитектура

Consumer и Producer используют confluent-kafka (librdkafka) с async обертками.
Пользовательский код - 100% async, Kafka I/O - в dedicated thread pool.
