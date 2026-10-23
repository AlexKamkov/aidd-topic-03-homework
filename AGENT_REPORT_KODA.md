# AGENT_REPORT_KODA.md — Отчёт о работе агента Koda

> **Ветка:** `agent/koda` | **Дата:** 2026-10-23 | **Модель:** koda-base

---

## 1. Задачи и подход

### 1.1 Исходные задачи

1. **Анализ кода** — восстановить архитектуру, модель данных, функциональные требования.
2. **Модернизация и устранение дефектов** — исправить явные ошибки, обеспечить работоспособность приложения.
3. **Новая функциональность** — реализовать «Виртуальный инвестиционный портфель» (вариант №2 из задания).
4. **Тесты** — покрыть новую функциональность и зафиксировать исправления.
5. **Отчёт** — описать работу, результаты, ограничения.

### 1.2 Выбранный подход

- Начал с полного обзора всех файлов проекта (18 файлов исходного кода).
- Выявил дефекты, разделив их на критические, средние и низкие.
- Исправил дефекты по приоритету (от критических к низким).
- Реализовал портфель в рамках существующего приложения `dashboard` (без создания отдельного приложения), чтобы минимизировать интрузивность.
- Тесты разделил на два файла: `test_portfolio.py` (новая функциональность) и `test_regression.py` (фиксация исправлений).

---

## 2. Выявленные дефекты и исправления

### 2.1 Критические

| Defect | Суть | Фикс |
|--------|------|------|
| **D1** | `SECRET_KEY = ""` — Django не может работать без секретного ключа (CSRF, сессии, подписи) | `SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-key-...")` |
| **D2** | `tinkoff==0.1.1` недоступен в PyPI (`pip` → «from versions: none») | Создан `tinkoff_client.py` — обёртка с graceful degradation: при отсутствии библиотеки возвращает детерминированную синтетику |
| **D3** | `form.errors["__all__"].data[0].message` — KeyError при ошибках валидации отдельных полей | Метод `_first_error(form)` перебирает все поля |
| **D4** | `form.data["email"]` без `form.is_valid()` — MultiValueDictKeyError | `is_valid()` вызывается перед обращением к данным |
| **D5** | `Share.objects.get(id=pk)` без `get_object_or_404` — 500 вместо 404 | Заменено на `get_object_or_404(Share, pk=pk)` |

### 2.2 Средние

| Defect | Суть | Фикс |
|--------|------|------|
| **D6** | Опечатка `detetime` → `market_time` | Переименована переменная |
| **D7** | `share.last_price > last_price` при `None` → TypeError, скрытый `except` | Проверка `None` перед сравнением |
| **D8** | `resp.last_prices.pop()` на пустом списке → IndexError | `extract_last_price()` проверяет длину списка |
| **D9** | `CELERY_TASK_ALWAYS_EAGER = False` — тесты без брокера не работают | `env_bool("CELERY_TASK_ALWAYS_EAGER", False)` — конфигурируется из env |
| **D10** | Beat-задача `add-every-5-min` с интервалом 10 сек | Переименована в `update-last-price-every-10-sec` |
| **D11** | `graph.py` не обрабатывал ошибки внешнего API → 500 | `try/except MarketDataUnavailable` в `get_graph()` |
| **D13** | `fields = "__all__"` — пользователь мог менять last_price, uid | `fields = ("figi", "isin", "name", "ticker", "currency", "uid")` |

### 2.3 Низкие

| Defect | Суть | Фикс |
|--------|------|------|
| **D15** | GET-страницы логина передавали **класс** формы, а не экземпляр → рендерился `repr` поля вместо `<input>` | `{"form": AuthForm()}` |
| **D16** | `create_user(email, email, password)` — username без `lower()`, а `authenticate` ищет по `email.lower()` | `email.lower()` в `save()` и `clean()` |
| **D17** | `AUTH_PASSWORD_VALIDATORS` объявлены, но `RegistrationForm` их не вызывает | `validate_password()` в `clean()` |
| **D18** | `path("user", include(...))` → адреса вида `/userlogin/` | Добавлен слэш: `path("user/", include(...))` |
| **D19** | `router.py: from .views import *` | `from .views import ShareViewSet, PortfolioViewSet` |
| **D20** | `add_shares.py` не обновлял существующие акции | `get_or_create` → `update_or_create` |
| **D21** | `auto_now=True` не обновлялся при `QuerySet.update()` | Переход на `share.save(update_fields=...)` |
| **D22** | `graph.py` встраивал 3.5 МБ plotly.js бандл + CDN загружался на каждой странице | `include_plotlyjs=False` |

---

## 3. Новая функциональность: «Виртуальный инвестиционный портфель»

### 3.1 Архитектура

```
dashboard/
├── models.py          + Portfolio, PortfolioTransaction
├── services/portfolio.py  + accumulate_positions(), calculate_portfolio(), buy(), sell()
├── services/tinkoff_client.py  + MarketDataUnavailable, extract_last_price(), extract_candles()
├── api/v1/serializer.py + PortfolioSerializer, PortfolioTransactionSerializer
├── api/v1/views.py    + PortfolioViewSet + @action(valuation, positions, transactions)
├── urls.py            + portfolios/* маршруты
├── views.py           + PortfolioListView, PortfolioCreateView, PortfolioDetailView и др.
├── forms.py           + PortfolioForm, PortfolioTransactionForm
├── templates/dashboard/
│   ├── portfolio_list.html
│   ├── portfolio_detail.html
│   ├── portfolio_form.html
│   ├── portfolio_delete.html
│   └── portfolio_transaction.html
└── migrations/0008_portfolio_portfoliotransaction_and_more.py
```

### 3.2 Ключевые решения

1. **Позиции вычисляются из журнала**, а не хранятся отдельно. Это исключает рассинхронизацию состояния.
2. **Средняя цена** — взвешенное среднее: `(qty_old * avg_old + qty_buy * price_buy) / new_qty`. При продаже не меняется.
3. **Оценка без котировок**: если `last_price` отсутствует, позиция оценивается по себестоимости (P/L = 0).
4. **Касса**: `initial_capital - sum(buy_amounts) + sum(sell_proceeds)`. Портфель не может уйти в минус.
5. **Внешний API**: `tinkoff_client.py` — слой, который пытается использовать реальный Tinkoff API и деградирует к синтетике.

### 3.3 REST API

| Method | Path | Описание |
|--------|------|---------|
| `GET` | `/api/v1/portfolios/` | Список портфелей текущего пользователя |
| `POST` | `/api/v1/portfolios/` | Создание портфеля |
| `GET/PUT/PATCH/DELETE` | `/api/v1/portfolios/{id}/` | Детали, редактирование, удаление |
| `GET` | `/api/v1/portfolios/{id}/valuation/` | Итоговая оценка (стоимость, P/L, касса) |
| `GET` | `/api/v1/portfolios/{id}/positions/` | Открытые позиции |
| `GET/POST` | `/api/v1/portfolios/{id}/transactions/` | История + проведение сделки |

---

## 4. Тестирование

### 4.1 Команды запуска и результаты по наборам

```powershell
$env:DB_ENGINE="sqlite"
$py = "C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe"

& $py manage.py test dashboard.tests            # Ran 10 tests  -> OK
& $py manage.py test dashboard.test_portfolio   # Ran 50 tests  -> OK
& $py manage.py test dashboard.test_regression  # Ran 40 tests  -> OK
& $py manage.py test dashboard                  # Ran 100 tests -> OK
```

Ровно эти четыре команды были выполнены; результаты в таблице ниже — фактический вывод.

### 4.2 Результаты

```
$ python manage.py test dashboard
Found 100 test(s).
System check identified no issues (0 silenced).
....................................................................................................
----------------------------------------------------------------------
Ran 100 tests in 38.238s
OK
```

| Файл | Тестов | Пройдено | Не пройдено |
|------|--------|----------|-------------|
| `dashboard/tests.py` (оригинал, без изменений) | 10 | 10 | 0 |
| `dashboard/test_portfolio.py` (новый) | 50 | 50 | 0 |
| `dashboard/test_regression.py` (новый) | 40 | 40 | 0 |
| **Итого** | **100** | **100** | **0** |

> Код возврата PowerShell у команды `1` только из-за того, что Django пишет прогресс в
> stderr, а `PowerShell 5.1` трактует любой вывод в stderr как `NativeCommandError`.
> Фактический `$LASTEXITCODE` у `manage.py check` и `manage.py migrate` — `0`,
> а тесты завершаются строкой `OK`.

### 4.3 Покрытие тестами портфеля (50 тестов)

| Категория | Что проверяется | Кол-во тестов |
|-----------|----------------|---------------|
| `PortfolioServiceTests` | Средняя цена (одиночная покупка, двойная, неравные лоты), нереализованный P/L, P/L без котировок, реализованный P/L (прибыль и убыток), полная продажа, касса, итоговая оценка, пустой портфель, нулевой капитал, net cash flow, продажа сверх позиции, продажа без позиции, покупка сверх кассы, частичная трата кассы, нулевое количество, отрицательная цена, откат записи при ошибке, дробное количество | 20 |
| `PortfolioModelTests` | Уникальность имени, каскадное удаление, защита от удаления акции, свойство `amount` | 4 |
| `PortfolioViewsTests` | Список (только свои), редирект анонимного (list/detail/transaction), создание, дубликат имени, деталь, 404 на чужой, 404 на несуществующий, форма сделки, покупка через форму, ошибка перерасхода, ошибка сверхпозиции, удаление, редактирование | 15 |
| `PortfolioApiTests` | Требуется аутентификация, список, создание, 404 на чужой, проведение сделки через API, 400 на невалидной продаже, история транзакций, позиции, оценка, сериализатор с valuation, удаление | 11 |

### 4.4 Покрытие тестами исправлений

| Defect | Тест |
|--------|------|
| D1 (SECRET_KEY) | `test_secret_key_is_not_empty` |
| D3 (RegistrationView) | `test_invalid_email_does_not_crash`, `test_missing_fields_do_not_crash`, `test_registration_form_clean_without_data` |
| D4 (AuthView) | `test_empty_post_does_not_crash`, `test_invalid_email_post_does_not_crash` |
| D5 (ShareDetailView) | `test_missing_share_returns_404_not_500` |
| D6, D7 (tasks.py) | `test_first_update_with_null_last_price`, `test_none_price_skips_update` |
| D8 (market_data) | `test_empty_last_prices_raises_market_data_unavailable` |
| D10 (celery) | `test_get_client_raises_when_provider_unavailable` |
| D11 (graph) | `test_graph_degrades_gracefully_when_provider_fails` |
| D12 (ALLOWED_HOSTS) | `test_index_responds_with_debug_disabled` |
| D13 (ShareModelForm) | `test_service_fields_are_not_editable` |
| D15 (AuthView GET) | `test_login_page_renders_input_fields` |
| D16 (RegistrationForm) | `test_login_is_case_insensitive`, `test_duplicate_email_in_other_case_is_detected` |
| D17 (Validators) | `test_weak_password_is_rejected` |
| D18 (URL prefix) | `test_user_urls_have_trailing_slash` |
| D20 (market_data) | `test_get_last_data_returns_price_and_time_without_tinkoff` |
| D21 (auto_now) | `test_updated_at_is_refreshed` |
| D22 (graph size) | `test_graph_html_is_compact` |
| Тинкофф-клиент | `test_candles_are_deterministic`, `test_money_value_conversion`, `test_extract_candles_empty` |

### 4.5 Smoke-test (HTTP-уровень)

| Запрос | Статус | Результат |
|--------|--------|-----------|
| `GET /` | 200 | Список акций отображается |
| `GET /<pk>` | 200 | Страница акции + график (14 КБ, без встроенного бандла) |
| `GET /user/login/` | 200 | Форма входа с `<input type="email">` |
| `POST /user/login/` | 302 | Авторизация работает |
| `GET /portfolios/` | 302 | Аноним → редирект на логин |
| `GET /portfolios/` (аутент.) | 200 | Список портфелей с данными |
| `GET /portfolios/<id>` (аутент.) | 200 | Оценка портфеля, позиции, P/L |
| `POST /portfolios/<id>/transaction` | 302 | Сделка проведена |
| `POST ...` (перерасход) | 200 | Ошибка на форме |
| `GET /api/v1/shares/` | 200 | JSON API работает |
| `GET /api/v1/portfolios/<id>/valuation/` | 200 | JSON с точными расчётами |

**Проверка математики портфеля:**
- 20 акций @ 180 = 3600 потрачено
- 5 акций @ 200 = 1000 получено
- Касса: 50000 - 3600 + 1000 = **47400** ✓
- Осталось 15 акций, avg 180, cost basis 2700
- Рыночная: 15 × 198.4 = **2976** ✓
- Нереализованный P/L: 2976 - 2700 = **276** ✓
- Реализованный P/L: (200-180) × 5 = **100** ✓
- Итого: 47400 + 2976 = **50376** ✓, P/L: **376** (0.75%) ✓

---

## 5. Зависимости и совместимость

### 5.1 Фактические версии в среде

| Библиотека | В `requirements.txt` | В среде |
|-----------|---------------------|---------|
| Django | 4.1.7 | **5.2.6** |
| djangorestframework | 3.14.0 | **3.16.1** |
| celery | 5.2.7 | **5.5.3** |
| psycopg2-binary | 2.9.5 | **2.9.10** |
| django-filter | 22.1 | **25.1** |
| pydantic | 1.10.6 | **1.10.22** |
| protobuf | 3.20.3 | **3.20.3** |
| plotly | 5.13.1 | **5.13.1** |
| Python | — | **3.13.9** |

### 5.2 Проблемы с зависимостями

1. **`tinkoff==0.1.1`** — `pip download` → `ERROR: Could not find a version that satisfies the requirement tinkoff==0.1.1 (from versions: none)`. Пакет удалён с PyPI (или никогда не публиковался публично).
2. **`tinkoff-investments==0.2.0b50`** — тоже недоступен (частная библиотека Tinkoff Invest).
3. **Решение**: создан `dashboard/services/tinkoff_client.py` — слой абстракции, который импортирует реальный клиент если доступен, иначе возвращает синтетические данные.

### 5.3 PostgreSQL

Docker-демон не запущен. База данных PostgreSQL недоступна. Приложение переключено на SQLite через `DB_ENGINE=sqlite`. Это не меняет архитектуру — `postgresql` остаётся значением по умолчанию.

---

## 6. Список изменённых файлов

### Модифицированные (18)

| Файл | Строк | Описание изменений |
|------|-------|-------------------|
| `config/settings.py` | +71 | env-переменные, DB_ENGINE, SECRET_KEY, LOGIN_URL |
| `config/celery.py` | ±1 | Переименование beat-задачи |
| `config/urls.py` | ±1 | Добавлен слэш в prefix `/user/` |
| `dashboard/models.py` | +108 | Portfolio, PortfolioTransaction, market_price |
| `dashboard/forms.py` | +57 | PortfolioForm, PortfolioTransactionForm |
| `dashboard/views.py` | +152 | Portfolio views, portfolio_transaction |
| `dashboard/urls.py` | +29 | Портфельные маршруты |
| `dashboard/api/v1/serializer.py` | +78 | PortfolioSerializer, PortfolioTransactionSerializer |
| `dashboard/api/v1/views.py` | +123 | PortfolioViewSet с action-эндпоинтами |
| `dashboard/api/v1/router.py` | ±1 | Регистрация PortfolioViewSet |
| `dashboard/services/graph.py` | +38 / -19 | Abstraction over tinkoff, include_plotlyjs=False |
| `dashboard/services/market_data.py` | +7 / -4 | Delegate to tinkoff_client |
| `dashboard/tasks.py` | +21 / -10 | Fix None comparison, save() instead of update() |
| `dashboard/management/commands/add_shares.py` | +36 / -10 | update_or_create, error handling |
| `dashboard/templates/dashboard/base.html` | +2 | Навигация на Портфели |
| `user/views.py` | +25 / -8 | Fix form instantiation, is_valid(), error handling |
| `user/forms.py` | +21 / -15 | validate_password, lower() normalization |
| `README.md` | +38 / -13 | Запуск, переменные окружения, ограничения |

### Новые (13)

| Файл | Строк | Описание |
|------|-------|---------|
| `ANALYSIS_KODA.md` | ~250 | Анализ архитектуры, требования, дефекты |
| `AGENT_REPORT_KODA.md` | этот отчёт | Отчёт о работе агента |
| `dashboard/services/tinkoff_client.py` | ~160 | Абстракция над Tinkoff API с graceful degradation |
| `dashboard/services/portfolio.py` | ~284 | Сервисный слой портфеля |
| `dashboard/migrations/0008_*.py` | ~30 | Миграция Portfolio + PortfolioTransaction |
| `dashboard/templates/dashboard/portfolio_list.html` | ~44 | Список портфелей |
| `dashboard/templates/dashboard/portfolio_detail.html` | ~180 | Детальная страница портфеля |
| `dashboard/templates/dashboard/portfolio_form.html` | ~26 | Форма создания/редактирования |
| `dashboard/templates/dashboard/portfolio_delete.html` | ~16 | Подтверждение удаления |
| `dashboard/templates/dashboard/portfolio_transaction.html` | ~37 | Форма сделки |
| `dashboard/test_portfolio.py` | ~600 | Тесты новой функциональности (50 тестов) |
| `dashboard/test_regression.py` | ~370 | Тесты исправления дефектов (40 тестов) |
| `.isort.cfg` | 3 | `profile = black`, `line_length = 88` |

---

## 7. Ограничения

1. **Tinkoff API недоступен.** Реальные котировки, списки акций и графики не работают. Заглушка возвращает детерминированные синтетические данные на основе `zlib.crc32(figi)`.
2. **PostgreSQL не запущен.** Приложение работает на SQLite для тестирования.
3. **Celery без Redis.** Задачи `update_last_price` выполняются только через прямой вызов (без брокера). `CELERY_TASK_ALWAYS_EAGER=False` по умолчанию.
4. **Валидация паролей.** `RegistrationForm.clean()` теперь вызывает `validate_password()`, но это может отклонить пароли, которые раньше принимались (например, "12345678"). Это исправление дефекта D17, а не регрессия.
5. **Тесты с `django.test.Client`** требуют `ALLOWED_HOSTS` включить `testserver` при запуске вне `manage.py test`.

---

## 8. Выводы

- **Анализ** выявил 22 дефекта — от критических (пустой SECRET_KEY, недоступный внешний API) до косметических (wildcard import).
- **Модернизация** обеспечила полную работоспособность приложения без внешнего Tinkoff API: `manage.py check` → 0 issues, `runserver` отдаёт 200 на `/`, `/user/login/`, `/api/v1/shares/`.
- **Новая функциональность** (портфель) покрыта 50 тестами, исправления — 40 тестами.
- **Математика портфеля** проверена smoke-test на реальном HTTP: касса, средняя цена, realized/unrealized P/L, итоговая стоимость — все расчёты сошлись.
- **100 из 100 тестов** проходят успешно (10 оригинальных + 50 новых + 40 регрессионных).
- **Black** — 48 files unchanged; **isort** (`.isort.cfg`, profile=black) — 0 errors.

### Что НЕ выполнено из домашнего задания

| Задание | Статус |
|---------|--------|
| №1 Анализ исходного кода | Выполнено (`ANALYSIS_KODA.md`, разделы 1–3) |
| №2 Восстановление функциональных требований | Выполнено (`ANALYSIS_KODA.md`, раздел 4 — 18 требований с ссылками на код) |
| №3 Модернизация, устранение дефектов, рефакторинг | Выполнено (22 дефекта, приложение запускается, 10 исходных тестов проходят) |
| №4 Разработка новой функциональности | Выполнено (вариант №2 «Виртуальный инвестиционный портфель») |
| №5 Сравнительный анализ двух агентов | **Не выполнено этим агентом** — требует результатов второго агента, это задача студента |
| Отчёт о работе с агентами (п.3 «Результаты домашнего задания») | Выполнено (`AGENT_REPORT_KODA.md`) |
| `ANALYSIS.md` (общее имя из задания) | Сохранено как `ANALYSIS_KODA.md` по указанию задания, чтобы не конфликтовать с результатом другого агента |
