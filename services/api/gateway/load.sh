#!/bin/bash

echo 'Gateway API starting!'

# Создание пользователя для безопасности (если не существует)
if ! id "user" &>/dev/null; then
    adduser --disabled-password --gecos '' --shell /bin/bash user
fi

chown -R user:user /usr/src/app

# Запуск приложения под пользователем
su user -c "uvicorn app.main:app --host 0.0.0.0 --port 8000"