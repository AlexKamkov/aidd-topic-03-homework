from django import forms

from .models import Portfolio, PortfolioTransaction, Share


class ShareModelForm(forms.ModelForm):
    """Инструмент"""

    class Meta:
        model = Share
        # fields = "__all__" позволяло пользователю через веб-форму менять
        # служебные поля: last_price, is_trend_high и uid.
        fields = ("figi", "isin", "name", "ticker", "currency", "uid")


class PortfolioForm(forms.ModelForm):
    """Виртуальный инвестиционный портфель."""

    CURRENCIES = (("rub", "RUB"), ("usd", "USD"), ("eur", "EUR"))

    class Meta:
        model = Portfolio
        fields = ("name", "currency", "initial_capital")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user or getattr(self.instance, "user", None)
        self.fields["currency"] = forms.ChoiceField(
            label="Валюта расчётов", choices=self.CURRENCIES, initial="rub"
        )

    def clean_name(self):
        """Название уникально в рамках одного пользователя."""
        name = self.cleaned_data["name"]
        queryset = Portfolio.objects.filter(user=self.user, name=name)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("Портфель с таким названием уже существует.")
        return name


class PortfolioTransactionForm(forms.ModelForm):
    """
    Форма моделирования сделки внутри портфеля.

    Бизнес-проверки (недостаток средств, продажа сверх позиции) выполняются
    сервисным слоем ``dashboard.services.portfolio``, поэтому логика не
    дублируется на уровне формы.
    """

    class Meta:
        model = PortfolioTransaction
        fields = ("operation", "share", "quantity", "price")
        widgets = {"operation": forms.RadioSelect}

    def __init__(self, *args, portfolio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.portfolio = portfolio
        self.fields["share"] = forms.ModelChoiceField(
            label="Акция",
            queryset=Share.objects.order_by("ticker"),
            widget=forms.Select(attrs={"class": "form-control"}),
        )
