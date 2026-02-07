## Api Client Lib

### Для чего нужна?

Библиотека `Api Client Lib` предоставляет универсальный клиент для работы с API. Она упрощает взаимодействие с внешними сервисами, обеспечивая:
- **Обработку ошибок**: автоматическое управление исключениями и возврат структурированных данных.
- **Повторные запросы**: возможность автоматического повторения запросов при временных ошибках.
- **Ограничение запросов в секунду**: контроль количества запросов для предотвращения превышения лимитов API.
- **Интеграция с tradeforge_logger**: структурированное логирование всех операций.

### Основные возможности

- **Поддержка всех HTTP-методов**: GET, POST, PUT, DELETE и других.
- **Гибкая настройка**:
  - Тайм-ауты запросов.
  - Ограничение количества повторных попыток.
  - Настройка заголовков и параметров запроса.
- **Асинхронная и синхронная работа**: Выбор клиента в зависимости от ваших потребностей.

### Преимущества использования

- **Простота интеграции**: Готовое решение для API-запросов.
- **Масштабируемость**: Подходит как для небольших скриптов, так и для сложных микросервисов.
- **Надежность**: Встроенные механизмы обработки ошибок и повторных попыток.

### Зависимости

Библиотека требует следующие зависимости:

```bash
pip install httpx
```

А также внутренние библиотеки проекта:
- `tradeforge_logger` - для структурированного логирования

### Использование в асинхронном режиме

Для выполнения асинхронных запросов используйте `AsyncApiClient`:

```python
import asyncio

from tradeforge_apiclient import AsyncApiClient


async def main() -> None:
    # Использование как context manager (рекомендуется)
    async with AsyncApiClient() as client:
        url = "https://api.example.com/data"

        # GET запрос с автоматическим парсингом JSON
        data = await client.get_page(url=url, method="get", json_format=True)
        print(data)

        # POST запрос с данными
        response = await client.get_page(
            url="https://api.example.com/create",
            method="post",
            json_data={"key": "value"},
            json_format=True
        )
        print(response)


if __name__ == "__main__":
    asyncio.run(main())
```


### Использование в синхронном режиме

Для выполнения синхронных запросов используйте `SyncApiClient`:

```python
from tradeforge_apiclient import SyncApiClient


def main():
    # Использование как context manager (рекомендуется)
    with SyncApiClient() as client:
        url = "https://api.example.com/data"

        # GET запрос с автоматическим парсингом JSON
        data = client.get_page(url=url, method="get", json_format=True)
        print(data)

        # POST запрос с данными
        response = client.get_page(
            url="https://api.example.com/create",
            method="post",
            json_data={"key": "value"},
            json_format=True
        )
        print(response)


if __name__ == "__main__":
    main()
```

### Использование RateLimiter

Для ограничения количества запросов можно использовать общий `RateLimiter` для нескольких клиентов:

```python
from tradeforge_apiclient import AsyncApiClient, RateLimiter

# Создаем лимитер: максимум 10 запросов за 1 секунду
limiter = RateLimiter(max_calls=10, period=1.0)

async def main():
    # Используем один лимитер для всех клиентов
    async with AsyncApiClient(limiter=limiter) as client1:
        async with AsyncApiClient(limiter=limiter) as client2:
            # Оба клиента будут использовать общий лимит
            await client1.get_page("https://api.example.com/endpoint1")
            await client2.get_page("https://api.example.com/endpoint2")
```
