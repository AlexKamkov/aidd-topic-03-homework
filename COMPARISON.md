# Comparison of AI Coding Agents

## 1. Overview

Two independent coding agents worked on the Investing Copilot application in separate checkouts and Git branches.

- **Copilot** (`agent/copilot`): implemented persistent share-price history, period-based price charts, and a price-history API.
- **Koda** (`agent/koda`): implemented a virtual investment portfolio with buy/sell transactions, position summaries, purchase cost, market value, and realized profit.

The agents implemented different features, so this comparison focuses on their reported results, tests, and limitations rather than claiming that one implementation is universally better.

## 2. Test Results

| Criterion | Copilot | Koda |
|---|---|---|
| Local test suite | 17 tests passed | 100 tests passed |
| Django system checks | Passed | Local checks reported successful |
| Migration consistency | Checked; no changes required | Reported successful |
| Live Tinkoff integration | Not fully verified | Not fully verified; synthetic market data was used because the Tinkoff SDK was unavailable |
| Full infrastructure integration | PostgreSQL, Redis, and Celery were not fully verified | Full production integration was not fully verified |

These results describe the recorded local test runs. They do not prove that every feature works in a production environment.

## 3. Feature Comparison

### Copilot

The implementation stores share-price history and makes it possible to view price changes over a selected period. It also adds an API for retrieving historical prices.

**Strength:** focuses on historical market data and price visualization.

**Limitation:** live market integration and the complete production infrastructure were not fully tested.

### Koda

The implementation adds a virtual investment portfolio, including buy and sell transactions, position summaries, purchase cost, market value, and realized profit.

**Strength:** focuses on tracking simulated investments and portfolio performance.

**Limitation:** the test run used synthetic market data because the Tinkoff SDK was unavailable. Live integration was not fully verified.

## 4. Agent Workflow and Problems

The agents used separate working copies and branches:

- Copilot: `investing-copilot`, branch `agent/copilot`.
- Koda: checkout currently named `investing-kilo`, branch `agent/koda`.

Kilo Code was initially attempted as the second agent, but its API Gateway returned HTTP 403. It did not complete the task. Koda was then used successfully as the second independent agent.

The exact elapsed time and complete iteration histories were not preserved. This report does not invent those measurements or claim to reproduce prompts that were not recorded.

## 5. Conclusion

Both agents delivered distinct features and passed their recorded local test suites. Copilot concentrated on share-price history and visualization, while Koda concentrated on virtual portfolio management.

The test counts alone do not establish that one agent produced better code: the implementations have different scopes, and their tests may cover different behavior. A fairer comparison would require common acceptance criteria and equivalent integration tests.

The main remaining limitation is the lack of complete verification against live market services and the full production infrastructure.