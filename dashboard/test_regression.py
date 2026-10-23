"""
Тесты, фиксирующие исправленные дефекты исходной версии приложения.

Каждый тест соответствует дефекту из ANALYSIS_KODA.md и проверяет, что
прежняя ошибка (500 / некорректный HTML / неверная логика) не возвращается.
"""
import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status

from dashboard.forms import ShareModelForm
from dashboard.models import Share
from dashboard.services import tinkoff_client
from dashboard.services.graph import get_graph
from dashboard.services.market_data import get_last_data
from dashboard.services.tinkoff_client import (
    MarketDataUnavailable,
    extract_candles,
    extract_last_price,
    get_candles,
    get_client,
    money_to_float,
)
from dashboard.tasks import update_last_price
from user.forms import RegistrationForm

User = get_user_model()


class AuthViewTests(TestCase):
    """D4, D15 — авторизация."""

    def test_login_page_renders_input_fields(self):
        """D15: форма передавалась классом, вместо <input> рендерился repr поля."""
        response = self.client.get(reverse("user:auth"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, '<input type="email"')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="password"')
        self.assertNotContains(response, "EmailField object")

    def test_empty_post_does_not_crash(self):
        """D4: form.data["email"] без is_valid() давал MultiValueDictKeyError."""
        response = self.client.post(reverse("user:auth"), {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Введите корректный email и пароль.")

    def test_invalid_email_post_does_not_crash(self):
        response = self.client.post(
            reverse("user:auth"), {"email": "not-an-email", "password": "x"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_wrong_password_shows_error(self):
        User.objects.create_user("a@example.com", "a@example.com", "Str0ngPass!23")

        response = self.client.post(
            reverse("user:auth"),
            {"email": "a@example.com", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Неверный логин или пароль")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_is_case_insensitive(self):
        """D16: раньше username сохранялся без приведения к нижнему регистру."""
        User.objects.create_user(
            "case@example.com", "case@example.com", "Str0ngPass!23"
        )

        response = self.client.post(
            reverse("user:auth"),
            {"email": "CASE@Example.COM", "password": "Str0ngPass!23"},
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_successful_login_redirects(self):
        User.objects.create_user("b@example.com", "b@example.com", "Str0ngPass!23")

        response = self.client.post(
            reverse("user:auth"),
            {"email": "b@example.com", "password": "Str0ngPass!23"},
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertRedirects(response, reverse("dashboard:index"))


class RegistrationViewTests(TestCase):
    """D3, D15, D16, D17 — регистрация."""

    def test_registration_page_renders_input_fields(self):
        """D15."""
        response = self.client.get(reverse("user:registration"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="password1"')
        self.assertContains(response, 'name="password2"')

    def test_invalid_email_does_not_crash(self):
        """D3: form.errors["__all__"].data[0] падал, когда ошибка была по полю."""
        response = self.client.post(
            reverse("user:registration"),
            {
                "email": "bad",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Регистрация в системе")

    def test_missing_fields_do_not_crash(self):
        response = self.client.post(reverse("user:registration"), {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_password_mismatch_shows_error(self):
        response = self.client.post(
            reverse("user:registration"),
            {
                "email": "c@example.com",
                "password1": "Str0ngPass!23",
                "password2": "OtherPass!45",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Введенные пароли не совпадают")

    def test_duplicate_email_shows_error(self):
        User.objects.create_user("d@example.com", "d@example.com", "Str0ngPass!23")

        response = self.client.post(
            reverse("user:registration"),
            {
                "email": "d@example.com",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "уже зарегистрирован")

    def test_duplicate_email_in_other_case_is_detected(self):
        """D16: дубликат в другом регистре раньше обходил проверку."""
        User.objects.create_user("e@example.com", "e@example.com", "Str0ngPass!23")

        response = self.client.post(
            reverse("user:registration"),
            {
                "email": "E@Example.com",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "уже зарегистрирован")

    def test_weak_password_is_rejected(self):
        """D17: объявленные AUTH_PASSWORD_VALIDATORS раньше не вызывались."""
        response = self.client.post(
            reverse("user:registration"),
            {
                "email": "f@example.com",
                "password1": "12345678",
                "password2": "12345678",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.filter(username="f@example.com").exists())

    def test_valid_registration_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("user:registration"),
            {
                "email": "g@example.com",
                "password1": "Str0ngPass!23",
                "password2": "Str0ngPass!23",
            },
        )

        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertTrue(User.objects.filter(username="g@example.com").exists())

    def test_registration_form_clean_without_data(self):
        """D3: clean() не должен падать с KeyError на пустой форме."""
        form = RegistrationForm(data={})

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class ShareDetailViewTests(TestCase):
    """D5 — детальная страница акции."""

    def test_missing_share_returns_404_not_500(self):
        response = self.client.get(reverse("dashboard:detail", args=[4242]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_existing_share_renders(self):
        share = Share.objects.create(
            figi="BBG000B9XRY4",
            isin="US0378331005",
            name="Apple",
            ticker="AAPL",
            currency="usd",
            uid="uid-1",
            last_price=100.5,
        )

        response = self.client.get(reverse("dashboard:detail", args=[share.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Apple")


class ShareModelFormTests(TestCase):
    """D13 — веб-форма не должна давать менять служебные поля."""

    def test_service_fields_are_not_editable(self):
        form = ShareModelForm()

        self.assertNotIn("last_price", form.fields)
        self.assertNotIn("is_trend_high", form.fields)
        self.assertNotIn("updated_at", form.fields)

    def test_instrument_fields_are_editable(self):
        form = ShareModelForm()

        for name in ("figi", "isin", "name", "ticker", "currency", "uid"):
            self.assertIn(name, form.fields)


class TasksTests(TestCase):
    """D6, D7 — Celery-задача обновления цен."""

    def _share(self, price=None):
        return Share.objects.create(
            figi="BBG000B9XRY4",
            isin="US0378331005",
            name="Apple",
            ticker="AAPL",
            currency="usd",
            uid="uid-1",
            last_price=price,
        )

    def test_first_update_with_null_last_price(self):
        """D7: сравнение None > float вызывало TypeError, скрытый except."""
        share = self._share(price=None)

        with patch(
            "dashboard.tasks.get_last_data",
            return_value=(120.0, datetime.datetime.now(datetime.timezone.utc)),
        ):
            update_last_price()

        share.refresh_from_db()
        self.assertEqual(share.last_price, 120.0)
        self.assertTrue(share.is_trend_high)

    def test_price_growth_sets_trend_high(self):
        share = self._share(price=100.0)

        with patch(
            "dashboard.tasks.get_last_data",
            return_value=(110.0, datetime.datetime.now(datetime.timezone.utc)),
        ):
            update_last_price()

        share.refresh_from_db()
        self.assertTrue(share.is_trend_high)

    def test_price_drop_sets_trend_low(self):
        share = self._share(price=100.0)

        with patch(
            "dashboard.tasks.get_last_data",
            return_value=(90.0, datetime.datetime.now(datetime.timezone.utc)),
        ):
            update_last_price()

        share.refresh_from_db()
        self.assertFalse(share.is_trend_high)

    def test_updated_at_is_refreshed(self):
        """D14: QuerySet.update() не применяет auto_now, updated_at устаревал."""
        share = self._share(price=100.0)
        before = share.updated_at

        with patch(
            "dashboard.tasks.get_last_data",
            return_value=(110.0, datetime.datetime.now(datetime.timezone.utc)),
        ):
            update_last_price()

        share.refresh_from_db()
        self.assertGreater(share.updated_at, before)

    def test_none_price_skips_update(self):
        share = self._share(price=100.0)

        with patch("dashboard.tasks.get_last_data", return_value=(None, None)):
            update_last_price()

        share.refresh_from_db()
        self.assertEqual(share.last_price, 100.0)

    def test_task_survives_service_error(self):
        share = self._share(price=100.0)

        with patch(
            "dashboard.tasks.get_last_data", side_effect=MarketDataUnavailable("boom")
        ):
            update_last_price()  # не должно бросить исключение наружу

        share.refresh_from_db()
        self.assertEqual(share.last_price, 100.0)


class TinkoffFallbackTests(TestCase):
    """D2, D8, D11 — деградация при недоступном внешнем API."""

    def setUp(self):
        self.share = Share.objects.create(
            figi="BBG000B9XRY4",
            isin="US0378331005",
            name="Apple",
            ticker="AAPL",
            currency="usd",
            uid="uid-1",
        )

    def test_market_data_returns_price_and_time_without_tinkoff(self):
        price, market_time = get_last_data(self.share)

        self.assertIsInstance(price, float)
        self.assertGreater(price, 0)
        self.assertIsNotNone(market_time)

    def test_candles_are_deterministic_without_tinkoff(self):
        first = get_candles(self.share, days=5)
        second = get_candles(self.share, days=5)

        self.assertEqual(len(first), 5)
        self.assertEqual([value for _, value in first], [value for _, value in second])

    def test_graph_html_is_compact(self):
        """Бандл plotly.js не должен встраиваться в каждую страницу."""
        plot_div = get_graph(self.share, days=5)

        self.assertIn("<div", plot_div)
        self.assertLess(len(plot_div), 200_000)

    @patch(
        "dashboard.services.graph.get_candles",
        side_effect=MarketDataUnavailable("down"),
    )
    def test_graph_degrades_gracefully_when_provider_fails(self, _mock):
        """D11: ошибка внешнего API больше не приводит к 500."""
        plot_div = get_graph(self.share)

        self.assertIn("недоступны", plot_div)

    def test_empty_last_prices_raises_market_data_unavailable(self):
        """D8: resp.last_prices.pop() на пустом списке давал IndexError."""
        response = SimpleNamespace(last_prices=[])

        with self.assertRaises(MarketDataUnavailable):
            extract_last_price(response, figi=self.share.figi)

    def test_empty_candle_list_returns_empty_series(self):
        self.assertEqual(extract_candles([]), [])

    def test_money_value_conversion_includes_nano(self):
        """Цена должна учитывать наноединицы, а не только целую часть."""
        money = SimpleNamespace(units=123, nano=456_000_000)

        self.assertAlmostEqual(money_to_float(money), 123.456)

    def test_plain_number_is_converted(self):
        self.assertAlmostEqual(money_to_float(10.5), 10.5)

    def test_get_client_raises_when_provider_unavailable(self):
        with self.assertRaises(MarketDataUnavailable):
            with get_client():
                pass

    def test_is_available_is_false_without_library(self):
        self.assertFalse(tinkoff_client._TINKOFF_INSTALLED)


class SettingsTests(TestCase):
    """D1, D9, D12 — настройки."""

    def test_secret_key_is_not_empty(self):
        from django.conf import settings

        self.assertTrue(settings.SECRET_KEY)

    def test_allowed_hosts_are_configured(self):
        from django.conf import settings

        self.assertIn("localhost", settings.ALLOWED_HOSTS)

    @override_settings(DEBUG=False)
    def test_index_responds_with_debug_disabled(self):
        """D12: с пустым ALLOWED_HOSTS приложение отдавало 400."""
        from django.conf import settings

        with self.settings(ALLOWED_HOSTS=settings.ALLOWED_HOSTS, DEBUG=False):
            response = self.client.get("/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class UrlPrefixTests(TestCase):
    """D12(b) — префикс пользовательских маршрутов."""

    def test_user_urls_have_trailing_slash(self):
        self.assertEqual(reverse("user:auth"), "/user/login/")
        self.assertEqual(reverse("user:registration"), "/user/registration/")
        self.assertEqual(reverse("user:logout"), "/user/logout/")


class LogoutViewTests(TestCase):
    """Выход из системы."""

    def test_logout_redirects_to_index(self):
        User.objects.create_user("h@example.com", "h@example.com", "Str0ngPass!23")
        self.client.force_login(User.objects.get(username="h@example.com"))

        response = self.client.get(reverse("user:logout"))

        self.assertRedirects(response, reverse("dashboard:index"))
