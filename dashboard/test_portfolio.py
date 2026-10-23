"""
Тесты новой функциональности — «Виртуальный инвестиционный портфель».

Проверяются бизнес-правила сервисного слоя, веб-интерфейс и REST API.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.models import Portfolio, PortfolioTransaction, Share
from dashboard.services.portfolio import (
    InsufficientPosition,
    NegativeCash,
    PortfolioError,
    buy,
    calculate_portfolio,
    net_cash_flow,
    sell,
)

User = get_user_model()


def make_share(ticker="AAPL", figi="BBG000B9XRY4", uid="uid-aapl", price=None):
    return Share.objects.create(
        ticker=ticker,
        figi=figi,
        isin="US0378331005",
        name=f"Company {ticker}",
        currency="usd",
        uid=uid,
        last_price=price,
    )


class PortfolioServiceTests(TestCase):
    """Бизнес-правила портфеля."""

    def setUp(self):
        self.user = User.objects.create_user(
            "tester@example.com", "tester@example.com", "Str0ngPass!23"
        )
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name="Тестовый",
            currency="usd",
            initial_capital=Decimal("10000.00"),
        )
        self.apple = make_share("AAPL", "BBG000B9XRY4", "uid-aapl", price=200.0)
        self.intel = make_share("INTC", "BBG000B9XRY5", "uid-intc", price=30.0)

    # --- Расчёт средней цены ---

    def test_single_buy_sets_average_price_and_cash(self):
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("150.00"))

        valuation = calculate_portfolio(self.portfolio)

        self.assertEqual(len(valuation.positions), 1)
        position = valuation.positions[0]
        self.assertEqual(position.quantity, Decimal("10"))
        self.assertEqual(position.average_price, Decimal("150.00"))
        # Касса: 10000 - 10*150
        self.assertEqual(valuation.cash, Decimal("8500.00"))

    def test_average_price_is_weighted_on_second_buy(self):
        """Средняя цена пересчитывается как взвешенное среднее."""
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("100.00"))
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("200.00"))

        position = calculate_portfolio(self.portfolio).positions[0]

        self.assertEqual(position.quantity, Decimal("20"))
        self.assertEqual(position.average_price, Decimal("150.00"))

    def test_average_price_with_unequal_lots(self):
        buy(self.portfolio, self.apple, Decimal("3"), Decimal("100.00"))
        buy(self.portfolio, self.apple, Decimal("7"), Decimal("200.00"))

        position = calculate_portfolio(self.portfolio).positions[0]

        # (3*100 + 7*200) / 10 = 170
        self.assertEqual(position.quantity, Decimal("10"))
        self.assertEqual(position.average_price, Decimal("170.00"))

    # --- Unrealized P/L ---

    def test_unrealized_pl_uses_last_price(self):
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("150.00"))
        self.apple.last_price = 200.0
        self.apple.save()

        valuation = calculate_portfolio(self.portfolio)
        position = valuation.positions[0]

        self.assertEqual(position.market_price, Decimal("200.0"))
        self.assertEqual(position.market_value, Decimal("2000.00"))
        self.assertEqual(position.unrealized_pl, Decimal("500.00"))
        self.assertEqual(valuation.unrealized_pl, Decimal("500.00"))

    def test_position_without_market_price_falls_back_to_cost(self):
        """Без котировки позиция оценивается по себестоимости, P/L = 0."""
        share = make_share("NONE", "BBG000B9XRY9", "uid-none", price=None)
        buy(self.portfolio, share, Decimal("5"), Decimal("10.00"))

        valuation = calculate_portfolio(self.portfolio)
        position = valuation.positions[0]

        self.assertFalse(position.has_market_price)
        self.assertIsNone(position.market_price)
        self.assertEqual(position.market_value, Decimal("50.00"))
        self.assertEqual(position.unrealized_pl, Decimal("0.00"))
        self.assertIsNone(position.unrealized_pl_percent)

    # --- Реализованный P/L при продаже ---

    def test_sell_calculates_realized_profit(self):
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("100.00"))
        sell(self.portfolio, self.apple, Decimal("4"), Decimal("150.00"))

        valuation = calculate_portfolio(self.portfolio)

        # Реализованная прибыль: (150 - 100) * 4 = 200
        self.assertEqual(valuation.realized_pl, Decimal("200.00"))
        # Позиция уменьшилась до 6 бумаг по средней 100
        self.assertEqual(valuation.positions[0].quantity, Decimal("6"))
        self.assertEqual(valuation.positions[0].average_price, Decimal("100.00"))
        # Касса: 10000 - 1000 + 600 = 9600
        self.assertEqual(valuation.cash, Decimal("9600.00"))

    def test_sell_at_loss_calculates_negative_realized_pl(self):
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("100.00"))
        sell(self.portfolio, self.apple, Decimal("10"), Decimal("80.00"))

        valuation = calculate_portfolio(self.portfolio)

        self.assertEqual(valuation.realized_pl, Decimal("-200.00"))
        self.assertEqual(valuation.positions, [])
        self.assertEqual(valuation.cash, Decimal("9800.00"))

    def test_full_sell_closes_position(self):
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("100.00"))
        sell(self.portfolio, self.apple, Decimal("10"), Decimal("120.00"))

        valuation = calculate_portfolio(self.portfolio)

        self.assertEqual(valuation.positions, [])
        self.assertEqual(valuation.market_value, Decimal("0.00"))
        self.assertEqual(valuation.total_value, Decimal("10200.00"))
        self.assertEqual(valuation.total_pl, Decimal("200.00"))
        self.assertEqual(valuation.total_pl_percent, Decimal("2.00"))

    # --- Итоговая оценка ---

    def test_total_value_counts_cash_and_positions(self):
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("150.00"))
        buy(self.portfolio, self.intel, Decimal("20"), Decimal("30.00"))

        valuation = calculate_portfolio(self.portfolio)

        # Позиции: 10*200 + 20*30 = 2600, касса: 10000-1500-600 = 7900
        self.assertEqual(valuation.market_value, Decimal("2600.00"))
        self.assertEqual(valuation.cash, Decimal("7900.00"))
        self.assertEqual(valuation.total_value, Decimal("10500.00"))
        self.assertEqual(valuation.total_pl, Decimal("500.00"))
        self.assertEqual(valuation.total_pl_percent, Decimal("5.00"))

    def test_empty_portfolio_returns_initial_capital(self):
        valuation = calculate_portfolio(self.portfolio)

        self.assertEqual(valuation.positions, [])
        self.assertEqual(valuation.cash, Decimal("10000.00"))
        self.assertEqual(valuation.total_value, Decimal("10000.00"))
        self.assertEqual(valuation.total_pl, Decimal("0.00"))

    def test_total_pl_percent_is_none_without_initial_capital(self):
        zero = Portfolio.objects.create(
            user=self.user, name="Без капитала", initial_capital=Decimal("0.00")
        )
        valuation = calculate_portfolio(zero)

        self.assertIsNone(valuation.total_pl_percent)

    def test_net_cash_flow_subtracts_sells(self):
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("100.00"))
        sell(self.portfolio, self.apple, Decimal("5"), Decimal("110.00"))

        # 1000 потрачено - 550 получено = 450 чистый отток
        self.assertEqual(net_cash_flow(self.portfolio), Decimal("450.00"))

    # --- Ограничения ---

    def test_sell_more_than_held_raises(self):
        buy(self.portfolio, self.apple, Decimal("5"), Decimal("100.00"))

        with self.assertRaises(InsufficientPosition):
            sell(self.portfolio, self.apple, Decimal("6"), Decimal("100.00"))

    def test_sell_without_position_raises(self):
        with self.assertRaises(InsufficientPosition):
            sell(self.portfolio, self.apple, Decimal("1"), Decimal("100.00"))

    def test_buy_beyond_cash_raises(self):
        with self.assertRaises(NegativeCash):
            buy(self.portfolio, self.apple, Decimal("100"), Decimal("200.00"))

    def test_buy_keeps_cash_non_negative_after_partial_spending(self):
        buy(self.portfolio, self.apple, Decimal("10"), Decimal("150.00"))
        # Осталось 8500 — покупка на 8600 должна быть отклонена
        with self.assertRaises(NegativeCash):
            buy(self.portfolio, self.intel, Decimal("10"), Decimal("860.00"))

    def test_zero_quantity_rejected(self):
        with self.assertRaises(PortfolioError):
            buy(self.portfolio, self.apple, Decimal("0"), Decimal("100.00"))
        with self.assertRaises(PortfolioError):
            sell(self.portfolio, self.apple, Decimal("0"), Decimal("100.00"))

    def test_negative_price_rejected(self):
        with self.assertRaises(PortfolioError):
            buy(self.portfolio, self.apple, Decimal("1"), Decimal("-1.00"))

    def test_failed_buy_does_not_write_transaction(self):
        before = PortfolioTransaction.objects.count()

        with self.assertRaises(NegativeCash):
            buy(self.portfolio, self.apple, Decimal("1000"), Decimal("200.00"))

        self.assertEqual(PortfolioTransaction.objects.count(), before)

    def test_fractional_quantity_is_supported(self):
        buy(self.portfolio, self.apple, Decimal("1.5"), Decimal("100.00"))

        position = calculate_portfolio(self.portfolio).positions[0]

        self.assertEqual(position.quantity, Decimal("1.5"))
        self.assertEqual(position.average_price, Decimal("100.00"))


class PortfolioModelTests(TestCase):
    """Ограничения модели."""

    def setUp(self):
        self.user = User.objects.create_user(
            "m@example.com", "m@example.com", "Str0ngPass!23"
        )
        self.other = User.objects.create_user(
            "o@example.com", "o@example.com", "Str0ngPass!23"
        )

    def test_portfolio_name_unique_per_user(self):
        from django.db.utils import IntegrityError

        Portfolio.objects.create(user=self.user, name="Основной")

        # У другого пользователя такое же название допустимо
        Portfolio.objects.create(user=self.other, name="Основной")
        self.assertEqual(Portfolio.objects.count(), 2)

        with self.assertRaises(IntegrityError):
            Portfolio.objects.create(user=self.user, name="Основной")

    def test_transaction_amount_property(self):
        portfolio = Portfolio.objects.create(
            user=self.user, name="П", initial_capital=Decimal("1000.00")
        )
        share = make_share("GSB", "BBG000B9XRY1", "uid-gsb")
        txn = PortfolioTransaction.objects.create(
            portfolio=portfolio,
            share=share,
            operation=PortfolioTransaction.Operation.BUY,
            quantity=Decimal("3"),
            price=Decimal("12.50"),
        )

        self.assertEqual(txn.amount, Decimal("37.50"))

    def test_deleting_portfolio_removes_transactions(self):
        portfolio = Portfolio.objects.create(user=self.user, name="П")
        share = make_share("DLT", "BBG000B9XRZ1", "uid-dlt")
        PortfolioTransaction.objects.create(
            portfolio=portfolio,
            share=share,
            operation=PortfolioTransaction.Operation.BUY,
            quantity=Decimal("1"),
            price=Decimal("1.00"),
        )

        portfolio.delete()

        self.assertEqual(PortfolioTransaction.objects.count(), 0)

    def test_deleting_share_with_transactions_is_protected(self):
        portfolio = Portfolio.objects.create(user=self.user, name="П")
        share = make_share("PRC", "BBG000B9XRZ2", "uid-prc")
        PortfolioTransaction.objects.create(
            portfolio=portfolio,
            share=share,
            operation=PortfolioTransaction.Operation.BUY,
            quantity=Decimal("1"),
            price=Decimal("1.00"),
        )

        with self.assertRaises(Exception):
            share.delete()


class PortfolioViewsTests(TestCase):
    """Веб-интерфейс портфеля."""

    def setUp(self):
        self.user = User.objects.create_user(
            "v@example.com", "v@example.com", "Str0ngPass!23"
        )
        self.client.force_login(self.user)
        self.share = make_share("NVTK", "BBG000B9XS00", "uid-nvtk", price=10.0)
        self.portfolio = Portfolio.objects.create(
            user=self.user, name="Мой", initial_capital=Decimal("5000.00")
        )

    def test_list_shows_only_own_portfolios(self):
        other = User.objects.create_user(
            "other@example.com", "other@example.com", "Str0ngPass!23"
        )
        Portfolio.objects.create(user=other, name="Чужой")

        response = self.client.get(reverse("dashboard:portfolio_list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Мой")
        self.assertNotContains(response, "Чужой")

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()

        response = self.client.get(reverse("dashboard:portfolio_list"))

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(
            response["Location"],
            f"/user/login/?next={reverse('dashboard:portfolio_list')}",
        )

    def test_anonymous_cannot_open_portfolio_detail(self):
        self.client.logout()

        response = self.client.get(
            reverse("dashboard:portfolio_detail", args=[self.portfolio.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("/user/login/", response["Location"])

    def test_anonymous_cannot_open_transaction_form(self):
        self.client.logout()

        response = self.client.get(
            reverse("dashboard:portfolio_transaction", args=[self.portfolio.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("/user/login/", response["Location"])

    def test_create_portfolio_via_post(self):
        response = self.client.post(
            reverse("dashboard:portfolio_create"),
            {"name": "Новый", "currency": "rub", "initial_capital": "1200.00"},
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        portfolio = Portfolio.objects.get(name="Новый")
        self.assertEqual(portfolio.user, self.user)
        self.assertEqual(portfolio.initial_capital, Decimal("1200.00"))

    def test_create_portfolio_rejects_duplicate_name(self):
        response = self.client.post(
            reverse("dashboard:portfolio_create"),
            {"name": "Мой", "currency": "rub", "initial_capital": "100.00"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "уже существует")
        self.assertEqual(Portfolio.objects.filter(name="Мой").count(), 1)

    def test_detail_renders_valuation(self):
        buy(self.portfolio, self.share, Decimal("100"), Decimal("10.00"))

        response = self.client.get(
            reverse("dashboard:portfolio_detail", args=[self.portfolio.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "NVTK")
        self.assertContains(response, "4000.00")  # свободные средства
        self.assertContains(response, "5000.00")  # итоговая стоимость

    def test_detail_of_foreign_portfolio_is_404(self):
        other = User.objects.create_user(
            "f@example.com", "f@example.com", "Str0ngPass!23"
        )
        foreign = Portfolio.objects.create(user=other, name="Чужой")

        response = self.client.get(
            reverse("dashboard:portfolio_detail", args=[foreign.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_of_missing_portfolio_is_404(self):
        response = self.client.get(reverse("dashboard:portfolio_detail", args=[4242]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_transaction_page_get(self):
        response = self.client.get(
            reverse("dashboard:portfolio_transaction", args=[self.portfolio.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Новая операция")

    def test_buy_via_web_form(self):
        response = self.client.post(
            reverse("dashboard:portfolio_transaction", args=[self.portfolio.pk]),
            {
                "operation": "BUY",
                "share": self.share.pk,
                "quantity": "50",
                "price": "10.00",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(PortfolioTransaction.objects.count(), 1)
        self.assertEqual(PortfolioTransaction.objects.get().operation, "BUY")

    def test_buy_beyond_cash_shows_form_error(self):
        response = self.client.post(
            reverse("dashboard:portfolio_transaction", args=[self.portfolio.pk]),
            {
                "operation": "BUY",
                "share": self.share.pk,
                "quantity": "1000",
                "price": "10.00",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Недостаточно свободных средств")
        self.assertEqual(PortfolioTransaction.objects.count(), 0)

    def test_sell_more_than_held_shows_form_error(self):
        buy(self.portfolio, self.share, Decimal("5"), Decimal("10.00"))

        response = self.client.post(
            reverse("dashboard:portfolio_transaction", args=[self.portfolio.pk]),
            {
                "operation": "SELL",
                "share": self.share.pk,
                "quantity": "500",
                "price": "10.00",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "в портфеле только")
        self.assertEqual(PortfolioTransaction.objects.count(), 1)

    def test_delete_portfolio(self):
        response = self.client.post(
            reverse("dashboard:portfolio_delete", args=[self.portfolio.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(Portfolio.objects.count(), 0)

    def test_update_portfolio_capital(self):
        response = self.client.post(
            reverse("dashboard:portfolio_update", args=[self.portfolio.pk]),
            {"name": "Мой", "currency": "usd", "initial_capital": "9999.00"},
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.portfolio.refresh_from_db()
        self.assertEqual(self.portfolio.initial_capital, Decimal("9999.00"))


class PortfolioApiTests(APITestCase):
    """REST API портфеля."""

    def setUp(self):
        self.user = User.objects.create_user(
            "api@example.com", "api@example.com", "Str0ngPass!23"
        )
        self.share = make_share("TSLA", "BBG000B9XS10", "uid-tsla", price=250.0)
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name="API-портфель",
            currency="usd",
            initial_capital=Decimal("1000.00"),
        )
        self.client.force_authenticate(user=self.user)

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/portfolios/")

        # DRF с SessionAuthentication отдаёт 403, с Basic — 401.
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_list_own_portfolios(self):
        response = self.client.get("/api/v1/portfolios/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "API-портфель")

    def test_create_assigns_current_user(self):
        response = self.client.post(
            "/api/v1/portfolios/",
            {"name": "Второй", "currency": "usd", "initial_capital": "500.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Portfolio.objects.get(name="Второй")
        self.assertEqual(created.user, self.user)

    def test_foreign_portfolio_is_not_visible(self):
        other = User.objects.create_user(
            "x@example.com", "x@example.com", "Str0ngPass!23"
        )
        foreign = Portfolio.objects.create(user=other, name="Чужой")

        response = self.client.get(f"/api/v1/portfolios/{foreign.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_transaction_via_api(self):
        response = self.client.post(
            f"/api/v1/portfolios/{self.portfolio.id}/transactions/",
            {
                "operation": "BUY",
                "share": self.share.id,
                "quantity": "2",
                "price": "250.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PortfolioTransaction.objects.count(), 1)

    def test_invalid_sell_returns_400(self):
        response = self.client.post(
            f"/api/v1/portfolios/{self.portfolio.id}/transactions/",
            {
                "operation": "SELL",
                "share": self.share.id,
                "quantity": "1",
                "price": "250.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_transaction_list_history(self):
        buy(self.portfolio, self.share, Decimal("1"), Decimal("200.00"))

        response = self.client.get(
            f"/api/v1/portfolios/{self.portfolio.id}/transactions/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["share_ticker"], "TSLA")
        self.assertEqual(Decimal(response.data[0]["amount"]), Decimal("200.00"))

    def test_positions_endpoint(self):
        buy(self.portfolio, self.share, Decimal("2"), Decimal("200.00"))

        response = self.client.get(f"/api/v1/portfolios/{self.portfolio.id}/positions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ticker"], "TSLA")
        self.assertEqual(Decimal(response.data[0]["average_price"]), Decimal("200.00"))
        self.assertEqual(Decimal(response.data[0]["market_value"]), Decimal("500.00"))

    def test_valuation_endpoint(self):
        buy(self.portfolio, self.share, Decimal("2"), Decimal("200.00"))

        response = self.client.get(f"/api/v1/portfolios/{self.portfolio.id}/valuation/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data["cash"]), Decimal("600.00"))
        self.assertEqual(Decimal(response.data["market_value"]), Decimal("500.00"))
        self.assertEqual(Decimal(response.data["total_value"]), Decimal("1100.00"))
        self.assertEqual(Decimal(response.data["total_pl"]), Decimal("100.00"))

    def test_portfolio_serializer_exposes_valuation(self):
        buy(self.portfolio, self.share, Decimal("2"), Decimal("200.00"))

        response = self.client.get(f"/api/v1/portfolios/{self.portfolio.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data["total_value"]), Decimal("1100.00"))
        self.assertEqual(response.data["positions_count"], 1)

    def test_delete_portfolio_via_api(self):
        response = self.client.delete(f"/api/v1/portfolios/{self.portfolio.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Portfolio.objects.count(), 0)
