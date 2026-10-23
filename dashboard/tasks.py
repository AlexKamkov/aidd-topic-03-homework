from config.celery import app
from config.settings import logger
from dashboard.models import PriceHistory, Share
from dashboard.services.market_data import get_last_data


@app.task
def update_last_price():
    for share in Share.objects.all().iterator():
        try:
            last_price, recorded_at = get_last_data(share)
            previous_price = share.last_price
            share.last_price = float(last_price)
            share.is_trend_high = (
                previous_price is None or share.last_price >= previous_price
            )
            share.save(update_fields=["last_price", "is_trend_high", "updated_at"])
            PriceHistory.objects.create(
                share=share, price=last_price, recorded_at=recorded_at
            )
        except Exception:
            logger.exception("Failed to update market data for share %s", share.id)
