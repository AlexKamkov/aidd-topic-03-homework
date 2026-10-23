# investing

## Запуск

```bash
# Переменная окружения DB_ENGINE=sqlite позволяет запустить без PostgreSQL
# (PostgreSQL по умолчанию, как в исходной версии)
$env:DB_ENGINE="sqlite"
$env:DJANGO_SECRET_KEY="your-secret-key"

# Миграции
python manage.py migrate

# Запуск сервера
python manage.py runserver
```

## Тесты

```bash
$env:DB_ENGINE="sqlite"
python manage.py test dashboard
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `DB_ENGINE` | `postgresql` | `postgresql` или `sqlite` |
| `DJANGO_SECRET_KEY` | dev-ключ | Ключ подписи CSRF/сессий (нужен только при DEBUG=True) |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Через запятую |
| `TINKOFF_TOKEN` | (пусто) | Токен Tinkoff Invest API. Если не задан, данные берутся из заглушки |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | Запускать Celery-задачи синхронно |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | URL брокера Celery |

## Ограничения

- Библиотеки `tinkoff` (0.1.1) и `tinkoff-investments` недоступны в PyPI. Приложение
  использует детерминированную заглушку для получения котировок и графиков.
- PostgreSQL для продакшена; SQLite по умолчанию для тестирования.
- Celery требует Redis (или RabbitMQ) для реальной асинхронной обработки задач.

