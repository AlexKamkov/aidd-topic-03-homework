from rest_framework import serializers

from dashboard.models import Portfolio, PortfolioTransaction, Share
from dashboard.services.portfolio import calculate_portfolio


class ShareSerializer(serializers.ModelSerializer):
    class Meta:
        model = Share
        fields = (
            "id",
            "figi",
            "isin",
            "name",
            "ticker",
            "currency",
            "last_price",
            "is_trend_high",
            "updated_at",
        )


class PortfolioTransactionSerializer(serializers.ModelSerializer):
    share_ticker = serializers.CharField(source="share.ticker", read_only=True)
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = PortfolioTransaction
        fields = (
            "id",
            "portfolio",
            "share",
            "share_ticker",
            "operation",
            "quantity",
            "price",
            "amount",
            "created_at",
        )
        # portfolio заполняется из URL вложенного маршрута
        extra_kwargs = {"portfolio": {"required": False, "write_only": True}}


class PortfolioSerializer(serializers.ModelSerializer):
    """Портфель вместе с расчётной оценкой (стоимость, P/L, касса)."""

    positions_count = serializers.SerializerMethodField()
    cash = serializers.SerializerMethodField()
    market_value = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()
    total_pl = serializers.SerializerMethodField()
    total_pl_percent = serializers.SerializerMethodField()

    class Meta:
        model = Portfolio
        fields = (
            "id",
            "name",
            "currency",
            "initial_capital",
            "created_at",
            "updated_at",
            "positions_count",
            "cash",
            "market_value",
            "total_value",
            "total_pl",
            "total_pl_percent",
        )
        read_only_fields = ("created_at", "updated_at")

    def get_valuation(self, obj):
        """Кэш расчёта в сериализаторе — одна итерация на объект."""
        cache = self.__dict__.setdefault("_valuation_cache", {})
        if obj.pk not in cache:
            cache[obj.pk] = calculate_portfolio(obj)
        return cache[obj.pk]

    def get_positions_count(self, obj):
        return len(self.get_valuation(obj).positions)

    def get_cash(self, obj):
        return self.get_valuation(obj).cash

    def get_market_value(self, obj):
        return self.get_valuation(obj).market_value

    def get_total_value(self, obj):
        return self.get_valuation(obj).total_value

    def get_total_pl(self, obj):
        return self.get_valuation(obj).total_pl

    def get_total_pl_percent(self, obj):
        return self.get_valuation(obj).total_pl_percent
