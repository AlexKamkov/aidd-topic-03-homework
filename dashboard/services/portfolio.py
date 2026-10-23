"""
Бизнес-логика виртуального инвестиционного портфеля.

Единственный источник правды — журнал операций ``PortfolioTransaction``.
Позиции (количество и средняя цена приобретения) вычисляются из журнала,
поэтому не рассинхронизируются при изменении истории.

Средняя цена приобретения пересчитывается как взвешенное среднее:

    avg_new = (qty_old * avg_old + qty_buy * price_buy) / (qty_old + qty_buy)

При продаже средняя цена не меняется, а реализованная прибыль/убыток равны
``(price_sell - avg) * qty_sell``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction as db_transaction

from dashboard.models import Portfolio, PortfolioTransaction, Share

TWO_PLACES = Decimal("0.01")

BUY = PortfolioTransaction.Operation.BUY
SELL = PortfolioTransaction.Operation.SELL


class PortfolioError(Exception):
    """Ошибка бизнес-правил портфеля."""


class InsufficientPosition(PortfolioError):
    """Нельзя продать больше, чем есть в портфеле."""


class NegativeCash(PortfolioError):
    """Недостаточно свободных средств для покупки."""


@dataclass
class Position:
    """Открытая позиция по одной акции."""

    share: Share
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal | None
    market_value: Decimal
    unrealized_pl: Decimal
    unrealized_pl_percent: Decimal | None
    has_market_price: bool


@dataclass
class PortfolioValuation:
    """Сводная оценка портфеля."""

    portfolio: Portfolio
    positions: list[Position] = field(default_factory=list)
    cost_basis: Decimal = Decimal("0.00")
    cash: Decimal = Decimal("0.00")
    market_value: Decimal = Decimal("0.00")
    realized_pl: Decimal = Decimal("0.00")
    unrealized_pl: Decimal = Decimal("0.00")
    total_value: Decimal = Decimal("0.00")
    total_pl: Decimal = Decimal("0.00")
    total_pl_percent: Decimal | None = None

    @property
    def currency(self) -> str:
        return self.portfolio.currency


def _quant(value: Decimal) -> Decimal:
    """Округление до копеек."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def accumulate_positions(portfolio: Portfolio):
    """
    Проходит журнал операций и возвращает ``(state, realized_pl)``.

    ``state`` — словарь ``share_id -> [quantity, cost, realized]``, где
    ``cost`` — совокупная стоимость открытой позиции по средней цене.
    """
    state: dict[int, list[Decimal]] = {}
    realized_pl = Decimal("0")

    transactions = portfolio.transactions.select_related("share").order_by(
        "created_at", "id"
    )

    for txn in transactions:
        amount = txn.quantity * txn.price
        bucket = state.setdefault(
            txn.share_id, [Decimal("0"), Decimal("0"), Decimal("0")]
        )
        qty, cost = bucket[0], bucket[1]

        if txn.operation == BUY:
            bucket[0] = qty + txn.quantity
            bucket[1] = cost + amount
        else:  # SELL
            if qty <= 0:
                raise InsufficientPosition(
                    f"Позиции по акции {txn.share.ticker} нет в портфеле — "
                    f"продажа невозможна"
                )
            if txn.quantity > qty:
                raise InsufficientPosition(
                    f"Нельзя продать {txn.quantity} {txn.share.ticker}: "
                    f"в портфеле только {qty}"
                )
            average = cost / qty
            left = qty - txn.quantity
            realized_delta = amount - average * txn.quantity
            bucket[0] = left
            bucket[1] = average * left
            bucket[2] += realized_delta
            realized_pl += realized_delta

    return state, realized_pl


def build_positions(state: dict[int, list[Decimal]]) -> list[Position]:
    """Превращает внутреннее состояние в список открытых позиций."""
    share_ids = [share_id for share_id, pos in state.items() if pos[0] > 0]
    shares = {share.id: share for share in Share.objects.filter(id__in=share_ids)}

    positions: list[Position] = []
    for share_id in share_ids:
        share = shares[share_id]
        qty, cost, _ = state[share_id]
        average = _quant(cost / qty)
        market_price = share.market_price

        if market_price is None:
            # Без котировки позиция оценивается по цене приобретения:
            # стоимость известна, прибыль/убыток равны нулю.
            market_value = _quant(cost)
            unrealized_pl = Decimal("0.00")
            unrealized_pl_percent = None
            has_market_price = False
        else:
            market_value = _quant(qty * market_price)
            unrealized_pl = _quant(market_value - cost)
            unrealized_pl_percent = _quant(unrealized_pl / cost * 100) if cost else None
            has_market_price = True

        positions.append(
            Position(
                share=share,
                quantity=qty,
                average_price=average,
                market_price=market_price,
                market_value=market_value,
                unrealized_pl=unrealized_pl,
                unrealized_pl_percent=unrealized_pl_percent,
                has_market_price=has_market_price,
            )
        )

    positions.sort(key=lambda position: position.share.ticker)
    return positions


def net_cash_flow(portfolio: Portfolio) -> Decimal:
    """Чистый денежный поток: суммы покупок минус суммы продаж."""
    total = Decimal("0")
    for txn in portfolio.transactions.all():
        amount = txn.amount
        if txn.operation == BUY:
            total += amount
        else:
            total -= amount
    return total


def calculate_portfolio(portfolio: Portfolio) -> PortfolioValuation:
    """Рассчитывает стоимость портфеля, свободные средства и прибыль/убыток."""
    state, realized_pl = accumulate_positions(portfolio)
    positions = build_positions(state)

    # Себестоимость берётся напрямую из накопленного состояния, чтобы
    # не накапливать погрешность округления средней цены.
    cost_basis = _quant(
        sum((pos[1] for pos in state.values() if pos[0] > 0), Decimal("0"))
    )
    market_value = _quant(sum((p.market_value for p in positions), Decimal("0")))
    unrealized_pl = _quant(market_value - cost_basis)

    cash = _quant(portfolio.initial_capital - net_cash_flow(portfolio))
    total_value = _quant(cash + market_value)
    total_pl = _quant(total_value - portfolio.initial_capital)
    total_pl_percent = (
        _quant(total_pl / portfolio.initial_capital * 100)
        if portfolio.initial_capital
        else None
    )

    return PortfolioValuation(
        portfolio=portfolio,
        positions=positions,
        cost_basis=cost_basis,
        cash=cash,
        market_value=market_value,
        realized_pl=_quant(realized_pl),
        unrealized_pl=unrealized_pl,
        total_value=total_value,
        total_pl=total_pl,
        total_pl_percent=total_pl_percent,
    )


@db_transaction.atomic
def buy(portfolio: Portfolio, share: Share, quantity, price) -> PortfolioTransaction:
    """
    Покупка акции.

    Проверяются корректность количества и цены, а также наличие свободных
    средств: виртуальный портфель не может уйти в минус по кассе.
    """
    quantity = _as_decimal(quantity)
    price = _as_decimal(price)

    if quantity <= 0:
        raise PortfolioError("Количество для покупки должно быть больше нуля")
    if price < 0:
        raise PortfolioError("Цена сделки не может быть отрицательной")

    cash = _quant(portfolio.initial_capital - net_cash_flow(portfolio))
    cost = _quant(quantity * price)
    if cost > cash:
        raise NegativeCash(
            f"Недостаточно свободных средств: доступно {cash}, требуется {cost}"
        )

    return PortfolioTransaction.objects.create(
        portfolio=portfolio,
        share=share,
        operation=BUY,
        quantity=quantity,
        price=price,
    )


@db_transaction.atomic
def sell(portfolio: Portfolio, share: Share, quantity, price) -> PortfolioTransaction:
    """Продажа акции — только в пределах открытой позиции."""
    quantity = _as_decimal(quantity)
    price = _as_decimal(price)

    if quantity <= 0:
        raise PortfolioError("Количество для продажи должно быть больше нуля")
    if price < 0:
        raise PortfolioError("Цена сделки не может быть отрицательной")

    state, _ = accumulate_positions(portfolio)
    held = state.get(share.id, [Decimal("0")])[0]

    if held <= 0:
        raise InsufficientPosition(
            f"Позиции по акции {share.ticker} нет в портфеле — продажа невозможна"
        )
    if quantity > held:
        raise InsufficientPosition(
            f"Нельзя продать {quantity} {share.ticker}: в портфеле только {held}"
        )

    return PortfolioTransaction.objects.create(
        portfolio=portfolio,
        share=share,
        operation=SELL,
        quantity=quantity,
        price=price,
    )
