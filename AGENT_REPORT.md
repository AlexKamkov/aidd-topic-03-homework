# Agent work report

## Work completed

- Inspected the assignment, README, Django configuration, app routes and
  views, API serializers/viewsets, models/migrations, scheduled tasks, market
  data and graph services, dependency pins, and existing tests.
- Added [ANALYSIS.md](ANALYSIS.md) with the architecture, stack, data model,
  code-supported functional requirements, and identified defects and
  ambiguities.
- Implemented persisted price history: a decimal history model and migration,
  quote capture during the scheduled update, a period selector on the share
  detail page, a locally rendered graph, and an API response with period
  prices and absolute/percentage changes.
- Fixed quote truncation and the missing-prior-price trend calculation;
  updated share timestamps through model saves; made unknown detail pages
  return 404; and moved database credentials and the Tinkoff token to
  environment-configurable settings.
- Updated core Django/REST/filter/gRPC/PostgreSQL dependency pins for the
  available Python 3.13 runtime and removed the separately pinned `tinkoff`
  distribution because application code uses the `tinkoff-investments`
  package's `tinkoff.invest` module.
- Added tests for period filtering, change calculations, invalid periods,
  missing shares, detail-page selection, and persistence from the scheduled
  quote update.

## Files changed

- [ANALYSIS.md](ANALYSIS.md) — architecture and numbered functional
  requirements with source references.
- [AGENT_REPORT.md](AGENT_REPORT.md) — this report.
- [README.md](README.md) — local SQLite test setup, environment token
  configuration, and the price-history API.
- [config/settings.py](config/settings.py) — environment-based secret,
  database, and Tinkoff token configuration.
- [requirements.txt](requirements.txt) — Python 3.13-compatible core
  dependency updates and removal of the unused `tinkoff` distribution.
- [dashboard/models.py](dashboard/models.py) and
  [dashboard/migrations/0008_pricehistory.py](dashboard/migrations/0008_pricehistory.py)
  — persisted price-history model/schema.
- [dashboard/services/market_data.py](dashboard/services/market_data.py) and
  [dashboard/tasks.py](dashboard/tasks.py) — full-precision quote handling
  and scheduled history persistence.
- [dashboard/services/graph.py](dashboard/services/graph.py),
  [dashboard/views.py](dashboard/views.py), and
  [dashboard/templates/dashboard/detail.html](dashboard/templates/dashboard/detail.html)
  — historical graph and selectable period.
- [dashboard/api/v1/views.py](dashboard/api/v1/views.py) — share price-history
  endpoint.
- [dashboard/tests.py](dashboard/tests.py) — seven new behavior tests.

## Commands and actual results

Validation used Python 3.13 (`py -3.13`). The default PostgreSQL configuration
was overridden for test/smoke runs:

```powershell
$env:DJANGO_SECRET_KEY='local-validation-key'
$env:DATABASE_ENGINE='django.db.backends.sqlite3'
$env:DATABASE_NAME=':memory:'
py -3.13 manage.py check
py -3.13 manage.py makemigrations --check --dry-run
py -3.13 manage.py test
```

- `manage.py check`: passed, no issues.
- `makemigrations --check --dry-run`: passed, no model/migration differences.
- `manage.py test`: **17 tests passed**.
- `manage.py migrate --noinput` on a temporary SQLite database: passed,
  including migration `dashboard.0008_pricehistory`.
- `manage.py runserver 127.0.0.1:8765 --noreload` with migrated SQLite:
  started successfully; `GET /` returned **HTTP 200**. The server and temporary
  database were stopped/removed after the smoke test.
- `black --check` and `isort --profile black --check-only` were run on changed
  Python files. Formatting was corrected and rechecked.
- `git diff --check`: passed.

## Errors and limitations

- Initially, the default `python` was Python 3.14 without pip or Django. The
  installed Python 3.13 launcher had pip, so validation proceeded there.
- The first `pip install -r requirements.txt` failed because the unused
  `tinkoff==0.1.1` distribution could not be resolved. After removing that
  unused dependency, installation still failed because
  `tinkoff-investments==0.2.0b50` could not be resolved by the configured
  package index; the corresponding public PyPI JSON endpoint also returned
  404. To run app checks and tests, the other requirements were installed
  using a temporary filtered requirements file that excluded Tinkoff SDK
  packages. The source manifest still declares the SDK needed for live market
  access.
- Docker Compose is installed, but its Linux engine was not running
  (`docker compose ps` could not connect to the Docker Desktop engine). The
  PostgreSQL/Redis stack and real worker were therefore not started.
- No Tinkoff token was available, and the SDK distribution was unavailable;
  live quote retrieval and initial instrument import were not verified. The
  quote update task was tested with a mocked market response.
- The application still has out-of-scope deployment concerns noted in
  [ANALYSIS.md](ANALYSIS.md), including `DEBUG = True`, no configured
  production secret by default, and anonymous CRUD through the REST API.
- New price history starts accruing only after migration and successful
  scheduled quote updates. No historical backfill is included.

## Unfinished work

- Resolve and pin an installable, maintained Tinkoff SDK distribution, then
  verify `pip install -r requirements.txt` and live integration in an
  authorized environment.
- Start PostgreSQL and Redis, run Celery Beat/worker, and validate ingestion
  against a configured market-data account.
- Decide whether REST API mutations should require authentication and replace
  the development settings with deployment-specific secure values before
  production use.

## Second-agent comparison status

Kilo Code was initially attempted as the second agent, but its API Gateway returned HTTP 403 and it did not complete the assignment. Koda was subsequently used successfully as the second independent coding agent in a separate checkout and branch.

Koda implemented a virtual investment portfolio with portfolio transactions, position summaries, and realized-profit calculations. Its work is documented in `ANALYSIS_KODA.md` and `AGENT_REPORT_KODA.md` in the Koda checkout.

The Koda test suite was independently run from the terminal with `py -3.13 manage.py test dashboard`: all 100 tests passed. The output included a warning that the Tinkoff SDK was unavailable and synthetic market data was used. Live market integration and HTTP endpoint behavior were not fully verified.

The two agents implemented different features:
- Copilot: persisted share-price history, period-based graph, and price-history API.
- Koda: virtual investment portfolio with purchase and sale transactions, cost and market-value summaries, and realized-profit calculations.

The Copilot work is committed and pushed on branch `agent/copilot`. The Koda work is committed and pushed on branch `agent/koda`; commit `a0f55a6`.

## Remaining assignment requirements and evidence

| Assignment requirement | Status | Evidence and remaining work |
|---|---|---|
| 1. Analyze the application architecture and code. | Completed by both agents. | `ANALYSIS.md` in the Copilot checkout and `ANALYSIS_KODA.md` in the Koda checkout. |
| 2. Recover numbered, source-supported functional requirements and ambiguities. | Completed by both agents. | Each analysis file documents requirements and source references. |
| 3. Audit dependencies, fix compatibility defects, refactor, and verify the app. | Partially verified. | Copilot: Django checks, migration consistency, and 17 tests passed locally. Koda: 100 tests passed locally, migration consistency and formatting checks reported successful. Live Tinkoff integration and PostgreSQL/Redis/Celery operation remain unverified. |
| 4. Implement and test one permitted new feature. | Completed by both agents, with stated limitations. | Copilot implemented price history. Koda implemented a virtual investment portfolio. Copilot's 17 tests and Koda's 100 tests passed in local runs. |
| 5. Compare results from two agents. | Completed. | The agents implemented different features. Their analysis and reports, test results, and limitations are documented in their respective checkouts. Kilo Code's earlier HTTP 403 was a failed attempt; Koda was the successful second agent. |
| 6. Use separate agent runs, copies, and branches. | Completed. | Copilot checkout/branch: `investing-copilot`, `agent/copilot`. Koda checkout/branch: `investing-koda`, `agent/koda`. The branches are committed and pushed to the fork. |
| 7. Report prompts, iterations, elapsed time, and agent-specific problems. | Partially completed. | Agent reports record the main task, commands, test results, and blockers. Exact elapsed time and complete iteration histories were not preserved. Kilo Code's failed attempt is documented separately from Koda's successful work. |
