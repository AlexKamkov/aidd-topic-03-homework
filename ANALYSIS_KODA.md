# ANALYSIS_KODA.md — Анализ проекта Investing Demo

> **Агент:** Koda | **Ветка:** `agent/koda`

---

## 1. Назначение и технологический стек

**Назначение:** Веб-приложение для мониторинга цен акций, интегрированное с Tinkoff Invest API. Позволяет просматривать список акций, смотреть графики изменения цен, добавлять/редактировать/удалять инструменты.

**Стек:**
- Python 3.13 + Django 4.1.7 (в requirements.txt) → **фактически Django 5.2.6** в среде выполнения
- Django REST Framework 3.14.0 → **фактически 3.16.1**
- PostgreSQL (Docker, docker-compose.yml)
- Redis (Docker, для Celery-брокера)
- Celery 5.2.7 → **фактически 5.5.3**
- Tinkoff Invest API (`tinkoff==0.1.1`, `tinkoff-investments==0.2.0b50`)
- Plotly 5.13.1 (графики)
- django-crispy-forms + crispy-bootstrap3 (шаблоны форм)
- django-filter, djangorestframework

---

## 2. Структура проекта

```
config/
├── __init__.py          # экспортирует celery_app
├── asgi.py              # ASGI-приложение
├── celery.py            # конфигурация Celery + beat-расписание
├── settings.py          # настройки Django
├── urls.py              # root-маршрутизация
├── wsgi.py              # WSGI-приложение
dashboard/
├── admin.py             # админка Share
├── apps.py              # AppConfig
├── forms.py             # ShareModelForm (ModelForm)
├── models.py            # Share
├── tasks.py             # Celery-задача update_last_price
├── tests.py             # API-тесты Share CRUD
├── urls.py              # URL-маршруты dashboard
├── views.py             # ListView/DetailView/Create/Update/Delete
├── api/v1/              # DRF ViewSet для REST API
├── services/
│   ├── market_data.py   # получение данных через Tinkoff API
│   └── graph.py         # построение графика через Tinkoff API
├── templates/dashboard/ # HTML-шаблоны (base, list, detail, create, delete)
├── management/commands/
│   └── add_shares.py    # команда для загрузки акций из Tinkoff
user/
├── models.py            # User = get_user_model() (не используется)
├── forms.py             # AuthForm, RegistrationForm
├── views.py             # AuthView, RegistrationView, LogoutView
├── urls.py              # login/registration/logout
├── templates/user/      # auth, registration, base
```

---

## 3. Архитектура и взаимодействие компонентов

### Маршрутизация
1. `config/urls.py` → root: `/` → `dashboard.urls`
2. `dashboard/urls.py`:
   - `/` → `ShareListView` (список акций)
   - `/<int:pk>` → `ShareDetailView` (детальная + график)
   - `create` → `ShareCreateView`
   - `update/<int:pk>` → `ShareUpdateView`
   - `delete/<int:pk>` → `ShareDeleteView`
   - `api/` → `dashboard.api.urls`
3. `dashboard/api/urls.py` → `v1/` → `dashboard.api.v1.urls`
4. `dashboard.api.v1/urls.py` → `router` → `ShareViewSet` (`/api/v1/shares/`)
5. `user/urls.py` → `user` prefix: `login/`, `registration/`, `logout/`

### Обработка запросов
- **MVT (Model-View-Template):** классические Django-представления
- **REST API:** DRF ViewSet с сериализатором, пагинацией, фильтрацией, поиском
- **Celery-задачи:** `update_last_price` запускается каждые 10 секунд, обновляет `last_price` и `is_trend_high` для всех акций через Tinkoff API

### Модель данных
- **Share** — акция: figi, isin, name, ticker, currency, uid, last_price, is_trend_high, updated_at
- **User** (default) — стандартная модель Django: email как username, стандартные поля

### Внешние зависимости
- `tinkoff.invest.Client` — Tinkoff Invest API (доступ к котировкам, свечам, списку акций)
- `plotly.offline.plot` — рендер графиков в HTML
- `redis` — Celery-брокер (localhost:6379)

---

## 4. Восстановленные функциональные требования

### 4.1 Аутентификация

| # | Требование | Подтверждение в коде |
|---|-----------|---------------------|
| 1 | Регистрация нового пользователя по email + password | `user/views.py:36-55`, `user/forms.py:8-53` |
| 2 | Авторизация по email + password | `user/views.py:8-33`, `user/forms.py:56-70` |
| 3 | Выход из системы | `user/views.py:58-63` |
| 4 | Защита создания/редактирования/удаления акций от неавторизованных | `dashboard/views.py:11-17` (IsUserAuthenticatedMixin) |

### 4.2 Управление акциями

| # | Требование | Подтверждение в коде |
|---|-----------|---------------------|
| 5 | Отображение списка акций с пагинацией (100 на страницу) | `dashboard/views.py:20-26`, `dashboard/templates/dashboard/list.html` |
| 6 | Детальная информация об акции с графиком цен | `dashboard/views.py:29-38`, `dashboard/services/graph.py` |
| 7 | Добавление новой акции | `dashboard/views.py:41-46`, `dashboard/templates/dashboard/create.html` |
| 8 | Редактирование акции | `dashboard/views.py:49-55`, `dashboard/templates/dashboard/create.html` |
| 9 | Удаление акции | `dashboard/views.py:58-62`, `dashboard/templates/dashboard/delete.html` |

### 4.3 REST API

| # | Требование | Подтверждение в коде |
|---|-----------|---------------------|
| 10 | GET /api/v1/shares/ — список акций с пагинацией и фильтрацией | `dashboard/api/v1/views.py`, `dashboard/api/v1/urls.py` |
| 11 | GET /api/v1/shares/{id}/ — детальная информация | `rest_framework.viewsets.ModelViewSet` |
| 12 | POST /api/v1/shares/ — создание акции | `rest_framework.viewsets.ModelViewSet` |
| 13 | PUT /api/v1/shares/{id}/ — обновление акции | `rest_framework.viewsets.ModelViewSet` |
| 14 | DELETE /api/v1/shares/{id}/ — удаление акции | `rest_framework.viewsets.ModelViewSet` |
| 15 | Поиск по name (точное совпадение), сортировка по name/ticker | `dashboard/api/v1/views.py:16-22` |

### 4.4 Автоматизация (Celery)

| # | Требование | Подтверждение в коде |
|---|-----------|---------------------|
| 16 | Периодическое обновление цен акций (каждые 10 сек) | `config/celery.py:13-17`, `dashboard/tasks.py:7-28` |
| 17 | Обновление is_trend_high при изменении цены | `dashboard/tasks.py:15-22` |

### 4.5 Команды управления

| # | Требование | Подтверждение в коде |
|---|-----------|---------------------|
| 18 | Загрузка списка акций из Tinkoff API | `dashboard/management/commands/add_shares.py` |

---

### 4.6 Виртуальный инвестиционный портфель (новая функциональность)

| # | Требование | Подтверждение в коде |
|---|-----------|---------------------|
| 19 | Создание персонального портфеля с начальным капиталом | `dashboard/models.py:Portfolio` |
| 20 | Покупка акций (BUY) — фиксация количества, цены, времени | `dashboard/models.py:PortfolioTransaction` |
| 21 | Продажа акций (SELL) — проверка наличия позиции, расчёт прибыли/убытка | `dashboard/models.py:PortfolioTransaction` + `dashboard/services/portfolio.py` |
| 22 | Текущая оценка портфеля: стоимость позиций + свободные средства | `dashboard/services/portfolio.py:calculate_portfolio` |
| 23 | История операций в портфеле | `dashboard/models.py:PortfolioTransaction` + `dashboard/templates/dashboard/portfolio_detail.html` |
| 24 | Защита от продажи большего объёма, чем есть в портфеле | `dashboard/services/portfolio.py:InsufficientPosition` |
| 25 | REST API для управления портфелем | `dashboard/api/v1/serializer.py:PortfolioSerializer` |

---

## 5. Выявленные дефекты и проблемы

### Критические

| # | Описание | Файл:строка | Влияние |
|---|---------|-------------|---------|
| D1 | `SECRET_KEY = ""` — пустой секретный ключ | `config/settings.py:6` | Django не работает: CSRF, сессии, криптография не функционируют |
| D2 | Пакет `tinkoff==0.1.1` недоступен в PyPI ("from versions: none") | `requirements.txt:35` | Весь функционал Tinkoff API сломан: market_data, graph, add_shares, tasks |
| D3 | `RegistrationView.post` — `form.errors["__all__"].data[0].message` — KeyError/IndexError при валидации отдельных полей | `user/views.py:54` | 500 при регистрации с невалидными данными |
| D4 | `AuthView.post` — `form.data["email"]` без `form.is_valid()` — MultiValueDictKeyError | `user/views.py:18-19` | 500 при авторизации без данных в POST |
| D5 | `ShareDetailView.get` — `Share.objects.get(id=pk)` без `get_object_or_404` | `dashboard/views.py:32` | 500 вместо 404 при несуществующей акции |

### Средние

| # | Описание | Файл:строка | Влияние |
|---|---------|-------------|---------|
| D6 | `tasks.py:13` — опечатка `detetime` вместо `datetime` | `dashboard/tasks.py:13` | Непоследовательное именование, но не влияет на логику (переменная используется только для возврата) |
| D7 | `tasks.py:16` — `share.last_price > last_price` при `last_price=None` вызывает TypeError, подавляемый общим `except` | `dashboard/tasks.py:16` | Скрывает ошибку, устанавливает `is_trend_high=True` без проверки |
| D8 | `market_data.py:8-9` — `resp.last_prices.pop()` при пустом списке вызывает IndexError | `dashboard/services/market_data.py:8-9` | 500 при отсутствии котировок |
| D9 | `settings.py:144` — `CELERY_TASK_ALWAYS_EAGER = False` — тесты без Celery-воркера не работают | `config/settings.py:144` | Тесты, не использующие брокер, падают |
| D10 | `config/celery.py:14` — расписание `add-every-5-min` с интервалом `10.0` секунд | `config/celery.py:14` | Несоответствие названия задачи и фактического интервала |
| D11 | `graph.py:14` — обращение к `client.get_all_candles()` невозможно проверить: пакет `tinkoff` не устанавливается (см. D2). Любая ошибка сети/токена приводит к 500 на странице `/<pk>`, потому что вызов не обёрнут в обработку ошибок | `dashboard/services/graph.py:11-36` | Страница детали акции падает при недоступном внешнем API |
| D12 | `settings.py:10` — `ALLOWED_HOSTS = []` — блокирует все запросы кроме Django internal | `config/settings.py:10` | При DEBUG=True работает, но при отключении — 400 |
| D13 | `dashboard/forms.py:10` — `fields = "__all__"` разрешает редактировать все поля включая uid, last_price, is_trend_high | `dashboard/forms.py:10` | Небезопасно: пользователь может изменить uid, цену, тренд |
| D14 | `tasks.py:24` — `Share.objects.filter(id=share.id).update()` создаёт отдельный запрос UPDATE вместо обновления объекта в памяти | `dashboard/tasks.py:24` | Неэффективность, но функционально корректно |
| D15 | В GET-обработчиках в контекст передаётся **класс** формы, а не экземпляр: `{"form": AuthForm}` / `{"form": RegistrationForm}` | `user/views.py:13`、`user/views.py:41` | Страницы входа и регистрации выводят `repr` поля вместо `<input>` — формы ввода фактически отсутствуют |
| D16 | `RegistrationForm.save()` сохраняет username без нормализации регистра, а `AuthView.post` ищет пользователя по `email.lower()` | `user/forms.py:49-52`, `user/views.py:19` | Пользователь, зарегистрированный как `User@Example.com`, не может войти |
| D17 | `AUTH_PASSWORD_VALIDATORS` объявлены в настройках, но `RegistrationForm` их не вызывает | `config/settings.py:106-119`, `user/forms.py:29-46` | Заявленное требование к паролям фактически не проверяется |

### Низкие (код-стайл / дублирование)

| # | Описание | Файл:строка | Влияние |
|---|---------|-------------|---------|
| L1 | `user/models.py` — пустой файл, только `User = get_user_model()` | `user/models.py:1` | Не используется, не мешает |
| L2 | `router.py:3` — `from .views import *` (wildcard import) | `dashboard/api/v1/router.py:3` | Плохая практика, линтер ругается |
| L3 | `list.html:35-38` — сложная вёрстка `<td>` с условием is_trend_high | `dashboard/templates/dashboard/list.html:35-38` | Работает, но читаемость низкая |
| L4 | `add_shares.py:22` — `get_or_create` без обновления существующих записей | `dashboard/management/commands/add_shares.py:22` | Не обновляет данные при повторном запуске |

---

## 6. Неоднозначности и пробелы

1. **Нет кастомной модели пользователя.** Пользователи создаются через `User.objects.create_user(email, email, password)` — email используется как username, но email не является уникальным в стандартной модели User.
2. **Нет механизма проверки email при регистрации.** Форма `RegistrationForm.clean()` проверяет дублирование email, но нет проверки уникальности на уровне БД (`unique=True` для email отсутствует).
3. **Нет настройки `DEFAULT_AUTO_FIELD` в settings (для Django 4.1 — BigAutoField по умолчанию, но для 5.x — BigAutoField, OK).**
4. **Нет инструкции по первичной настройке:** как получить TINKOFF_TOKEN, как запустить PostgreSQL, как выполнить миграции.
5. **Нет `.env` файла для секретов.** Токен Tinkoff должен храниться в переменной окружения или env-файле.

---

## 7. Требования к новой функциональности (Задание №4)

Реализован вариант **№2 «Виртуальный инвестиционный портфель»**. Вариант №3
(история изменения рыночных цен) не выбирался по условию работы; вариант №1
(персональный мониторинг) требует внешних push-уведомлений, которые невозможно
проверить без реального Tinkoff API.

### 7.1 Функциональные требования

| # | Требование | Реализация |
|---|-----------|-----------|
| NF1 | Пользователь может создавать собственные портфели и видеть только свои | `Portfolio.user` FK + `PortfolioViewSet.get_queryset` |
| NF2 | Название портфеля уникально в рамках пользователя | `UniqueConstraint` + `PortfolioForm.clean_name` |
| NF3 | Моделирование покупки акции: количество и цена сделки | `services.portfolio.buy()` |
| NF4 | Моделирование продажи акции | `services.portfolio.sell()` |
| NF5 | Учёт количества и средней цены приобретения по каждой акции | `accumulate_positions()` — взвешенное среднее |
| NF6 | Продажа больше имеющейся позиции запрещена | `InsufficientPosition` |
| NF7 | Покупка сверх свободных средств запрещена | `NegativeCash` |
| NF8 | Текущая стоимость портфеля считается по рыночным ценам | `calculate_portfolio().market_value` |
| NF9 | Расчёт нереализованной прибыли/убытка по открытым позициям | `Position.unrealized_pl`, `PortfolioValuation.unrealized_pl` |
| NF10 | Расчёт реализованной прибыли/убытка по закрытым сделкам | `PortfolioValuation.realized_pl` |
| NF11 | Итоговый результат: стоимость, P/L в деньгах и процентах | `total_value`, `total_pl`, `total_pl_percent` |
| NF12 | Просмотр истории операций портфеля | `PortfolioTransaction` + страница портфеля + `GET /transactions/` |
| NF13 | Веб-интерфейс: список, создание, правка, удаление, сделка | `dashboard/templates/dashboard/portfolio_*.html` |
| NF14 | REST API для программной работы с портфелем | `/api/v1/portfolios/…` |
| NF15 | Отсутствие котировки не ломает оценку портфеля | fallback на себестоимость, `has_market_price=False` |

### 7.2 Изменения в модели данных

Добавлены две сущности (миграция `dashboard/migrations/0008_portfolio_portfoliotransaction_and_more.py`):

```
Portfolio                     PortfolioTransaction
  user      -> AUTH_USER_MODEL   portfolio -> Portfolio (CASCADE)
  name                      share     -> Share (PROTECT)
  currency                  operation -> BUY | SELL
  initial_capital           quantity  -> Decimal(14,6)
  created_at / updated_at   price     -> Decimal(14,6)
                            created_at
```

Позиции **не** хранятся отдельной таблицей: они вычисляются из журнала
операций, поэтому журнал остаётся единственным источником правды и не может
рассинхронизироваться с позициями.

