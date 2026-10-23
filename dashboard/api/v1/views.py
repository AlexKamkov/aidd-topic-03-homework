from django.db import transaction as db_transaction
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dashboard.models import Portfolio, PortfolioTransaction, Share
from dashboard.services.portfolio import PortfolioError
from dashboard.services.portfolio import buy as portfolio_buy
from dashboard.services.portfolio import calculate_portfolio
from dashboard.services.portfolio import sell as portfolio_sell

from .serializer import (
    PortfolioSerializer,
    PortfolioTransactionSerializer,
    ShareSerializer,
)


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


class PortfolioViewSet(viewsets.ModelViewSet):
    """
    Персональные виртуальные портфели.

    Видимы только портфели текущего пользователя; чужой портфель
    отдаёт 404, а не 403, чтобы не раскрывать существование объекта.
    """

    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = (OrderingFilter,)
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"])
    def valuation(self, request, pk=None):
        """Итоговая оценка портфеля: стоимость, касса, прибыль/убыток."""
        portfolio = self.get_object()
        valuation = calculate_portfolio(portfolio)
        return Response(
            {
                "portfolio_id": portfolio.id,
                "currency": valuation.currency,
                "initial_capital": portfolio.initial_capital,
                "cash": valuation.cash,
                "cost_basis": valuation.cost_basis,
                "market_value": valuation.market_value,
                "total_value": valuation.total_value,
                "realized_pl": valuation.realized_pl,
                "unrealized_pl": valuation.unrealized_pl,
                "total_pl": valuation.total_pl,
                "total_pl_percent": valuation.total_pl_percent,
                "positions_count": len(valuation.positions),
            }
        )

    @action(detail=True, methods=["get"])
    def positions(self, request, pk=None):
        """Открытые позиции с количеством и средней ценой приобретения."""
        portfolio = self.get_object()
        valuation = calculate_portfolio(portfolio)
        return Response(
            [
                {
                    "share_id": position.share.id,
                    "ticker": position.share.ticker,
                    "name": position.share.name,
                    "currency": position.share.currency,
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "market_price": position.market_price,
                    "market_value": position.market_value,
                    "unrealized_pl": position.unrealized_pl,
                    "unrealized_pl_percent": position.unrealized_pl_percent,
                    "has_market_price": position.has_market_price,
                }
                for position in valuation.positions
            ]
        )

    @action(
        detail=True,
        methods=["get", "post"],
        url_path="transactions",
    )
    def transactions(self, request, pk=None):
        """История операций и проведение новой сделки (BUY/SELL)."""
        portfolio = self.get_object()

        if request.method == "GET":
            serializer = PortfolioTransactionSerializer(
                portfolio.transactions.select_related("share"), many=True
            )
            return Response(serializer.data)

        serializer = PortfolioTransactionSerializer(data=request.data)
        serializer.initial_data.pop("portfolio", None)
        serializer.is_valid(raise_exception=True)

        share = serializer.validated_data["share"]
        quantity = serializer.validated_data["quantity"]
        price = serializer.validated_data["price"]
        operation = serializer.validated_data["operation"]

        try:
            with db_transaction.atomic():
                if operation == PortfolioTransaction.Operation.BUY:
                    txn = portfolio_buy(portfolio, share, quantity, price)
                else:
                    txn = portfolio_sell(portfolio, share, quantity, price)
        except PortfolioError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            PortfolioTransactionSerializer(txn).data,
            status=status.HTTP_201_CREATED,
        )
