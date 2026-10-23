# Investing Demo: architecture and recovered requirements

## Application and technology

Investing Demo is a Django application for maintaining a catalogue of shares,
showing current market prices and trends, and exposing the catalogue through an
HTML interface and a REST API. The backend uses Django 5.2, Django REST
Framework, django-filter, PostgreSQL by default, Celery with Redis, Plotly, and
the Tinkoff Invest SDK. The dependencies are pinned in
[requirements.txt](requirements.txt).

## Structure and request flow

- [config/settings.py](config/settings.py#L13) configures Django apps,
  middleware, REST pagination/filter support, logging, the database and the
  Celery broker. PostgreSQL remains the default; database connection values
  can be overridden using environment variables.
- [config/urls.py](config/urls.py#L4) mounts the admin, dashboard, and user
  routes. The dashboard routes in [dashboard/urls.py](dashboard/urls.py#L13)
  serve the share list and detail pages, authenticated share forms, and the
  versioned API.
- [dashboard/views.py](dashboard/views.py#L21) implements the HTML list and
  detail views and authenticated create, update, and delete views. The list is
  ordered by name and paginated at 100 records.
- [dashboard/api/v1/views.py](dashboard/api/v1/views.py#L22) implements
  share CRUD through a DRF `ModelViewSet`; its serializer is defined in
  [dashboard/api/v1/serializer.py](dashboard/api/v1/serializer.py#L6).
  The API uses Django ORM queries, name/ticker filters, name search, ordering,
  and the global limit/offset pagination configured in settings.
- [user/urls.py](user/urls.py#L7) and [user/views.py](user/views.py#L8)
  provide registration, login, and logout using Django's built-in user model.
- [dashboard/management/commands/add_shares.py](dashboard/management/commands/add_shares.py#L8)
  imports share instruments from Tinkoff. The periodic task in
  [dashboard/tasks.py](dashboard/tasks.py#L8) requests quotes through
  [dashboard/services/market_data.py](dashboard/services/market_data.py#L6).
  Celery Beat schedules it every 10 seconds in
  [config/celery.py](config/celery.py#L13).
- The task stores current quote values in the share table and individual price
  observations in `PriceHistory`. The detail page renders a Plotly chart using
  those stored observations through
  [dashboard/services/graph.py](dashboard/services/graph.py#L10). The API
  history action is available at `/api/v1/shares/<id>/history/?days=30`.

## Data model and persistence

`Share`, defined in [dashboard/models.py](dashboard/models.py#L5), represents
an instrument. Its fields are FIGI, ISIN, company name, ticker, currency, Tinkoff
UID, current price, trend direction, and last-update timestamp. FIGI, ticker,
and UID are unique. A share has no owner or other original model relationship.

`PriceHistory`, defined in
[dashboard/models.py](dashboard/models.py#L25), has a many-to-one foreign key
to `Share` with cascade deletion, a decimal price, and the quote timestamp. Its
share/timestamp index supports time-window queries. The schema change is
captured in [dashboard/migrations/0008_pricehistory.py](dashboard/migrations/0008_pricehistory.py).

The ORM uses PostgreSQL by default as configured in
[config/settings.py](config/settings.py#L92); `DATABASE_ENGINE` can select
SQLite for local tests. Existing migrations are under
[dashboard/migrations/](dashboard/migrations/). Celery uses Redis by default;
the README instructs operators to start the database, Beat, and worker
separately.

## Recovered original functional requirements

1. The system shall display a share catalogue ordered by company name, with up
   to 100 items per page. **Evidence:** [dashboard/views.py](dashboard/views.py#L21),
   [dashboard/templates/dashboard/list.html](dashboard/templates/dashboard/list.html).
2. A visitor shall be able to open a share detail page and see its name,
   latest stored price, currency, last update time, and (when the market API is
   available) a recent historical-price graph. **Evidence:**
   [dashboard/urls.py](dashboard/urls.py#L15),
   [dashboard/templates/dashboard/detail.html](dashboard/templates/dashboard/detail.html),
   [dashboard/services/graph.py](dashboard/services/graph.py).
3. An authenticated user shall be able to create, update, and delete shares
   through the HTML forms. **Evidence:** [dashboard/views.py](dashboard/views.py#L11),
   [dashboard/urls.py](dashboard/urls.py#L16).
4. A user shall be able to register, authenticate, and log out through the
   account routes. **Evidence:** [user/urls.py](user/urls.py#L7),
   [user/views.py](user/views.py#L8).
5. The REST API shall provide paginated CRUD operations for shares and expose
   their identifier, instrument identifiers, name, ticker, currency, price,
   trend, and update time. **Evidence:**
   [dashboard/api/v1/views.py](dashboard/api/v1/views.py#L22),
   [dashboard/api/v1/serializer.py](dashboard/api/v1/serializer.py#L6),
   [config/settings.py](config/settings.py#L32).
6. API consumers shall be able to filter shares by name or ticker, search by
   name, and order by name or ticker. **Evidence:**
   [dashboard/api/v1/views.py](dashboard/api/v1/views.py#L16).
7. The scheduled market-data task shall retrieve a quote for each share and
   update its current price and trend. **Evidence:**
   [config/celery.py](config/celery.py#L13),
   [dashboard/tasks.py](dashboard/tasks.py#L8),
   [dashboard/services/market_data.py](dashboard/services/market_data.py#L6).
8. An operator shall be able to populate the share catalogue from the Tinkoff
   instrument service using the `add_shares` management command.
   **Evidence:** [dashboard/management/commands/add_shares.py](dashboard/management/commands/add_shares.py#L8).

## Added price-history feature requirements

1. The scheduled quote update shall persist each received price and its quote
   timestamp for that share. **Evidence:**
   [dashboard/tasks.py](dashboard/tasks.py#L8),
   [dashboard/models.py](dashboard/models.py#L25),
   [dashboard/migrations/0008_pricehistory.py](dashboard/migrations/0008_pricehistory.py).
2. A visitor shall be able to select a supported period for the share graph,
   and an API client shall be able to request prices for a period of 1 to 3650
   days. **Evidence:** [dashboard/views.py](dashboard/views.py#L30),
   [dashboard/templates/dashboard/detail.html](dashboard/templates/dashboard/detail.html),
   [dashboard/services/graph.py](dashboard/services/graph.py#L10),
   [dashboard/api/v1/views.py](dashboard/api/v1/views.py#L30).
3. The history API shall return observations in the selected period and the
   absolute and percentage change between the first and last observations
   (null when insufficient data exists or percentage change has a zero base).
   **Evidence:** [dashboard/api/v1/views.py](dashboard/api/v1/views.py#L30),
   [dashboard/tests.py](dashboard/tests.py#L130).

## Defects, limitations, and ambiguities

- The original code used a floating point current price and truncated the
  quote's fractional nanounits when updating it. Historical observations now
  use decimal storage, and current price updates include the fractional quote.
- The original graph made a separate live candle request whenever a detail
  page loaded and did not persist observations. It now plots locally stored
  task-collected data; historical coverage begins only after deployment of the
  new migration and subsequent successful quote updates.
- The original update task did not persist `updated_at` through `QuerySet.update`
  and treated a missing previous price through exception handling. It now saves
  the model timestamp and handles an unset prior price explicitly.
- The HTML share mutations require an authenticated user, but the REST
  `ModelViewSet` does not define permissions; the API currently permits
  anonymous CRUD. Whether the API should require authentication is not
  specified by the assignment.
- The meaning of `is_trend_high` is not specified beyond the display label.
  This implementation preserves its apparent interpretation: current quote is
  compared with the previous stored price. The original code sets it true when
  a prior price is missing.
- The history percentage is calculated relative to the first observation in
  the selected interval, not a market close or an exact interval boundary. A
  zero starting price yields no percentage change.
- The schedule interval is configured as 10 seconds. Neither the README nor
  the assignment specifies an update interval or market-data usage limits.
- The settings retain `DEBUG = True`, an empty default secret, and
  `ALLOWED_HOSTS = []`; production deployment requires secure values. The
  Tinkoff token also must be provided for live quote updates and initial
  catalogue import.
- The pinned Tinkoff SDK is an old beta dependency and was unavailable from
  the configured package index during this run. Live market integration could
  therefore not be exercised; its import is deferred so local app/tests do not
  require a configured external market account.
