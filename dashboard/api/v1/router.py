from rest_framework import routers

from .views import PortfolioViewSet, ShareViewSet

router = routers.DefaultRouter()
router.register(r"shares", ShareViewSet)
router.register(r"portfolios", PortfolioViewSet, basename="portfolio")
