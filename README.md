# investing

# PostgreSQL (Docker)
docker-compose -f docker-compose.yml up

# Локальный запуск тестов без PostgreSQL (PowerShell)
$env:DJANGO_SECRET_KEY="local-test-key"
$env:DATABASE_ENGINE="django.db.backends.sqlite3"
$env:DATABASE_NAME="$env:TEMP\investing-test.sqlite3"
py -3.13 manage.py test

# Tinkoff Invest API
# TINKOFF_TOKEN задается переменной среды

# Первоначальная загрузка списка акций
python manage.py add_shares

# Celery Beat
celery -A config beat

# Celery Worker
celery -A config worker -l info

# Celery Worker для Windows (Eventlet)
pip install eventlet cryptography
celery -A config worker -l info -P eventlet

# API
# /api/v1/shares — работа с акциями
# /api/v1/shares/<id>/history/?days=30 — история цены и изменение за период

# История цен
# Celery сохраняет полученные цены в PriceHistory.
# На странице акции можно выбрать период графика; данные загружаются из БД.
