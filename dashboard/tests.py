from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.models import PriceHistory, Share
from dashboard.tasks import update_last_price


class DashboardTests(APITestCase):
    def setUp(self) -> None:
        self.apple_share = Share.objects.create(
            figi="BBG000B9XRY4",
            isin="US0378331005",
            name="Apple",
            ticker="AAPL",
            currency="usd",
            uid="a9eb4238-eba9-488c-b102-b6140fd08e38",
            last_price=100.50,
            is_trend_high=True,
        )

        self.second_company = {
            "figi": "BBG000B9XRY5",
            "isin": "US0378331004",
            "name": "Company_test",
            "ticker": "TESTTEST",
            "currency": "usd",
            "uid": "a9eb4238-eba9-488c-b102-b6140fd08e39",
            "last_price": 1.50,
            "is_trend_high": False,
        }

    def test_share_list_html(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_share_list(self):
        response = self.client.get("/api/v1/shares/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        apple_share = response.json().get("results")[0]
        self.assertEqual(apple_share["id"], self.apple_share.id)
        self.assertEqual(apple_share["figi"], self.apple_share.figi)
        self.assertEqual(apple_share["isin"], self.apple_share.isin)
        self.assertEqual(apple_share["name"], self.apple_share.name)
        self.assertEqual(apple_share["ticker"], self.apple_share.ticker)
        self.assertEqual(apple_share["currency"], self.apple_share.currency)

    def test_share_detail(self):
        response = self.client.get("/api/v1/shares/")
        share_detail = response.json().get("results")[0]
        response = self.client.get(f"/api/v1/shares/{share_detail['id']}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_share_detail_invalid(self):
        response = self.client.get("/api/v1/shares/2/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_share_update(self):
        response = self.client.get("/api/v1/shares/")
        share_detail = response.json().get("results")[0]
        response = self.client.put(
            f"/api/v1/shares/{share_detail['id']}/",
            {
                "id": share_detail["id"],
                "figi": self.apple_share.figi,
                "isin": self.apple_share.isin,
                "name": f"{self.apple_share.name}_test",
                "ticker": self.apple_share.ticker,
                "currency": self.apple_share.currency,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["figi"], self.apple_share.figi)
        self.assertEqual(body["name"], f"{self.apple_share.name}_test")

    def test_share_update_invalid(self):
        response = self.client.get("/api/v1/shares/")
        share_detail = response.json().get("results")[0]
        response = self.client.put(
            f"/api/v1/shares/{share_detail['id']}/",
            {
                "figi": self.apple_share.figi,
                "name": f"{self.apple_share.name}_test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_create(self):
        response = self.client.post(
            "/api/v1/shares/", self.second_company, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(body["figi"], self.second_company["figi"])
        self.assertEqual(body["name"], self.second_company["name"])
        self.assertEqual(body["ticker"], self.second_company["ticker"])

        response = self.client.get("/api/v1/shares/")
        self.assertEqual(len(response.data["results"]), 2)

    def test_share_create_invalid(self):
        response = self.client.post(
            "/api/v1/shares/", {"figi": "BBG000B9XRY5"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_delete(self):
        response = self.client.get("/api/v1/shares/")
        share_detail = response.json().get("results")[0]
        response = self.client.delete(f"/api/v1/shares/{share_detail['id']}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        response = self.client.get("/api/v1/shares/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_share_delete_invalid(self):
        response = self.client.delete("/api/v1/shares/3/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_price_history_returns_prices_and_period_change(self):
        now = timezone.now()
        PriceHistory.objects.create(
            share=self.apple_share,
            price=Decimal("100.500000000"),
            recorded_at=now - timedelta(days=2),
        )
        PriceHistory.objects.create(
            share=self.apple_share,
            price=Decimal("110.000000000"),
            recorded_at=now - timedelta(days=1),
        )

        response = self.client.get(
            f"/api/v1/shares/{self.apple_share.id}/history/?days=30"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["prices"]), 2)
        self.assertEqual(response.data["absolute_change"], Decimal("9.500000000"))
        self.assertEqual(
            response.data["percentage_change"],
            Decimal("9.452736318407960199004975124"),
        )

    def test_price_history_rejects_invalid_period(self):
        response = self.client.get(
            f"/api/v1/shares/{self.apple_share.id}/history/?days=0"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_price_history_excludes_out_of_period_prices(self):
        PriceHistory.objects.create(
            share=self.apple_share,
            price=Decimal("90"),
            recorded_at=timezone.now() - timedelta(days=31),
        )

        response = self.client.get(
            f"/api/v1/shares/{self.apple_share.id}/history/?days=30"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["prices"], [])
        self.assertIsNone(response.data["absolute_change"])

    @patch("dashboard.tasks.get_last_data")
    def test_price_update_persists_exact_price_history(self, get_last_data):
        get_last_data.return_value = (Decimal("100.123456789"), timezone.now())

        update_last_price.run()

        self.apple_share.refresh_from_db()
        self.assertAlmostEqual(self.apple_share.last_price, 100.123456789)
        self.assertEqual(
            self.apple_share.price_history.get().price, Decimal("100.123456789")
        )

    def test_history_endpoint_returns_not_found_for_unknown_share(self):
        response = self.client.get("/api/v1/shares/999/history/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_share_detail_displays_history_for_selected_period(self):
        PriceHistory.objects.create(
            share=self.apple_share,
            price=Decimal("100"),
            recorded_at=timezone.now() - timedelta(days=5),
        )

        response = self.client.get(
            reverse("dashboard:detail", args=[self.apple_share.id]), {"days": 30}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.context["days"], 30)
        self.assertContains(response, 'value="30" selected')

    def test_share_detail_rejects_invalid_history_period(self):
        response = self.client.get(
            reverse("dashboard:detail", args=[self.apple_share.id]), {"days": "bad"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
