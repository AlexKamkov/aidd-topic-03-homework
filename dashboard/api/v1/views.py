from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from dashboard.models import Share

from .serializer import ShareSerializer


class ShareFilter(filters.FilterSet):
    class Meta:
        model = Share
        fields = ("name", "ticker")


class ShareViewSet(viewsets.ModelViewSet):
    serializer_class = ShareSerializer
    queryset = Share.objects.all()
    filter_backends = (OrderingFilter, filters.DjangoFilterBackend, SearchFilter)
    filterset_class = ShareFilter
    ordering_fields = ["name", "ticker"]
    search_fields = ["$name"]

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        try:
            days = int(request.query_params.get("days", 180))
        except (TypeError, ValueError):
            return Response(
                {"days": "Must be an integer between 1 and 3650."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not 1 <= days <= 3650:
            return Response(
                {"days": "Must be an integer between 1 and 3650."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        share = self.get_object()
        prices = list(
            share.price_history.filter(
                recorded_at__gte=timezone.now() - timedelta(days=days)
            ).order_by("recorded_at")
        )
        absolute_change = None
        percentage_change = None
        if len(prices) >= 2:
            first_price = prices[0].price
            last_price = prices[-1].price
            absolute_change = last_price - first_price
            if first_price != Decimal("0"):
                percentage_change = absolute_change / first_price * Decimal("100")

        return Response(
            {
                "ticker": share.ticker,
                "days": days,
                "prices": [
                    {
                        "recorded_at": item.recorded_at,
                        "price": item.price,
                    }
                    for item in prices
                ],
                "absolute_change": absolute_change,
                "percentage_change": percentage_change,
            }
        )
