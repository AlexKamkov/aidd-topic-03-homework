from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Share(models.Model):
    """Акция"""

    figi = models.CharField(max_length=255, unique=True)
    isin = models.CharField(max_length=255)
    name = models.CharField(max_length=255, verbose_name="Наименование компании")
    ticker = models.CharField(max_length=10, unique=True, verbose_name="Тикер")
    currency = models.CharField(max_length=20, verbose_name="Валюта")
    uid = models.CharField(max_length=255, unique=True)
    last_price = models.FloatField(blank=True, null=True, verbose_name="Текущая цена")
    is_trend_high = models.BooleanField(
        blank=True, null=True, verbose_name="Растет цена"
    )
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        verbose_name = "Акция"
        verbose_name_plural = "Акции"

    def __str__(self):
        return f"{self.ticker} — {self.name}"

    @property
    def market_price(self):
        """Цена для оценки: последняя котировка либо None, если её нет."""
        return Decimal(str(self.last_price)) if self.last_price is not None else None


class Portfolio(models.Model):
    """Виртуальный инвестиционный портфель пользователя."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios",
        verbose_name="Владелец",
    )
    name = models.CharField(max_length=255, verbose_name="Название")
    currency = models.CharField(
        max_length=20, default="rub", verbose_name="Валюта расчётов"
    )
    initial_capital = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Начальный капитал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлён")

    class Meta:
        verbose_name = "Портфель"
        verbose_name_plural = "Портфели"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_portfolio_name_per_user",
            )
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("dashboard:portfolio_detail", kwargs={"pk": self.pk})


class PortfolioTransaction(models.Model):
    """Операция покупки/продажи акции внутри портфеля."""

    class Operation(models.TextChoices):
        BUY = "BUY", "Покупка"
        SELL = "SELL", "Продажа"

    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="Портфель",
    )
    share = models.ForeignKey(
        Share,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="Акция",
    )
    operation = models.CharField(
        max_length=4, choices=Operation.choices, verbose_name="Операция"
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        verbose_name="Количество",
    )
    price = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="Цена сделки",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата операции")

    class Meta:
        verbose_name = "Операция портфеля"
        verbose_name_plural = "Операции портфеля"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return (
            f"{self.get_operation_display()} {self.share.ticker} "
            f"x{self.quantity} @ {self.price}"
        )

    @property
    def amount(self):
        """Сумма сделки."""
        return self.quantity * self.price
