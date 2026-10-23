"""
Единая точка доступа к Tinkoff Invest API.

Пакеты ``tinkoff`` и ``tinkoff-investments`` из requirements.txt отсутствуют в
PyPI (``pip`` отвечает «from versions: none»), поэтому приложение не должно
терять работоспособность из-за невозможности их установить.

Реальный клиент используется, только если библиотека импортирована и задан
``TINKOFF_TOKEN``. Иначе модуль возвращает детерминированные синтетические
данные, а страница акции остаётся рабочей.
"""
from __future__ import annotations

import datetime
import random
import zlib
from contextlib import contextmanager

from config.settings import TINKOFF_TOKEN, logger

try:  # реальная библиотека опциональна
    from tinkoff.invest import CandleInterval, Client
    from tinkoff.invest.utils import now as tinkoff_now

    _TINKOFF_INSTALLED = True
except ImportError:  # pragma: no cover - зависит от окружения
    CandleInterval = None
    Client = None
    tinkoff_now = None
    _TINKOFF_INSTALLED = False
    logger.warning(
        "Пакет tinkoff.invest не установлен — рыночные данные будут синтетическими"
    )


class MarketDataUnavailable(Exception):
    """Рыночные данные недоступны."""


def is_available() -> bool:
    """True, если библиотека установлена и токен задан."""
    return _TINKOFF_INSTALLED and bool(TINKOFF_TOKEN)


@contextmanager
def get_client():
    """Контекст-менеджер реального клиента Tinkoff Invest."""
    if not is_available():
        raise MarketDataUnavailable(
            "Tinkoff Invest API недоступен: пакет не установлен "
            "или не задан TINKOFF_TOKEN."
        )
    with Client(TINKOFF_TOKEN) as client:
        yield client


# ---------------------------------------------------------------------------
# Разбор ответов API вынесен в чистые функции, чтобы логику можно было
# проверить без установленной библиотеки.
# ---------------------------------------------------------------------------
def money_to_float(money) -> float:
    """Конвертирует MoneyValue (units + nano) в float."""
    units = getattr(money, "units", None)
    if units is None:
        return float(money)
    nano = getattr(money, "nano", 0) or 0
    return float(units) + nano / 1_000_000_000


def extract_last_price(response, figi: str):
    """
    Достаёт последнюю цену из ответа ``get_last_prices``.

    Пустой список раньше приводил к ``IndexError`` из ``list.pop()`` — теперь
    поднимается осмысленное ``MarketDataUnavailable``.
    """
    prices = getattr(response, "last_prices", None) or []
    if not prices:
        raise MarketDataUnavailable(f"Нет котировок для figi={figi}")
    item = prices[0]
    return money_to_float(item.price), item.time


def extract_candles(candles) -> list:
    """Разбирает список свечей в ``(date, close)``."""
    return [(candle.time.date(), money_to_float(candle.close)) for candle in candles]


# ---------------------------------------------------------------------------
# Синтетические данные для режима без внешнего API
# ---------------------------------------------------------------------------
def _seed_for_share(figi: str) -> int:
    """Детерминированное seed-число из figi (стабильно между запусками)."""
    return zlib.crc32((figi or "").encode("utf-8"))


def _synthetic_price(figi: str) -> float:
    rng = random.Random(_seed_for_share(figi))
    return round(rng.uniform(50, 500), 2)


def _stub_last_data(share):
    return _synthetic_price(share.figi), datetime.datetime.now(datetime.timezone.utc)


def _stub_candles(share, days: int) -> list:
    rng = random.Random(_seed_for_share(share.figi))
    base = _synthetic_price(share.figi)
    today = datetime.date.today()
    return [
        (
            today - datetime.timedelta(days=offset),
            round(base * (1 + rng.uniform(-0.05, 0.05)), 2),
        )
        for offset in range(days, 0, -1)
    ]


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------
def get_last_data(share):
    """Возвращает ``(price, time)`` последней котировки акции."""
    if is_available():
        with get_client() as client:
            response = client.market_data.get_last_prices(figi=[share.figi])
            price, market_time = extract_last_price(response, share.figi)
        logger.info(f"Get last data for share with id {share.id}")
        return price, market_time

    price, market_time = _stub_last_data(share)
    logger.info(f"Get stub last data for share with id {share.id}")
    return price, market_time


def get_candles(share, days: int = 180) -> list:
    """Возвращает ряд ``(date, close)`` за последние *days* дней."""
    if is_available():
        moment = (
            tinkoff_now()
            if tinkoff_now
            else datetime.datetime.now(datetime.timezone.utc)
        )
        with get_client() as client:
            candles = client.get_all_candles(
                figi=share.figi,
                from_=moment - datetime.timedelta(days=days),
                interval=CandleInterval.CANDLE_INTERVAL_DAY,
            )
            series = extract_candles(candles)
        logger.info(f"Get {len(series)} candles for share with id {share.id}")
        return series

    return _stub_candles(share, days)


def list_instruments():
    """Список акций из API инструмента (только реальный режим)."""
    with get_client() as client:
        return list(client.instruments.shares().instruments)
