from django.urls import include, path

from dashboard.views import (
    PortfolioCreateView,
    PortfolioDeleteView,
    PortfolioDetailView,
    PortfolioListView,
    PortfolioUpdateView,
    ShareCreateView,
    ShareDeleteView,
    ShareDetailView,
    ShareListView,
    ShareUpdateView,
    portfolio_transaction,
)

app_name = "dashboard"

urlpatterns = [
    path("", ShareListView.as_view(), name="index"),
    path("<int:pk>", ShareDetailView.as_view(), name="detail"),
    path("create", ShareCreateView.as_view(), name="create"),
    path("update/<int:pk>", ShareUpdateView.as_view(), name="update"),
    path("delete/<int:pk>", ShareDeleteView.as_view(), name="delete"),
    # --- Виртуальный инвестиционный портфель ---
    path("portfolios/", PortfolioListView.as_view(), name="portfolio_list"),
    path("portfolios/create", PortfolioCreateView.as_view(), name="portfolio_create"),
    path(
        "portfolios/<int:pk>",
        PortfolioDetailView.as_view(),
        name="portfolio_detail",
    ),
    path(
        "portfolios/<int:pk>/edit",
        PortfolioUpdateView.as_view(),
        name="portfolio_update",
    ),
    path(
        "portfolios/<int:pk>/delete",
        PortfolioDeleteView.as_view(),
        name="portfolio_delete",
    ),
    path(
        "portfolios/<int:portfolio_pk>/transaction",
        portfolio_transaction,
        name="portfolio_transaction",
    ),
    path("api/", include("dashboard.api.urls")),
]
