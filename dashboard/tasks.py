from config.celery import app
from config.settings import logger
from dashboard.models import Share
from dashboard.services.market_data import get_last_data


@app.task
def update_last_price():
    shares = Share.objects.all()

    for share in shares:
        try:
            # Исправлена опечатка detetime -> market_time
            last_price, market_time = get_last_data(share)

            if last_price is None:
                logger.warning(f"No price data for share id={share.id}, skipping")
                continue

            # Корректная обработка None в share.last_price: при первой загрузке
            # last_price=None, и сравнение None > float вызывало TypeError.
            if share.last_price is None:
                is_trend_high = True
            else:
                is_trend_high = last_price > share.last_price

            # save() вместо QuerySet.update(): только Model.save() применяет
            # auto_now к updated_at, поэтому время обновления оставалось
            # устаревшим на странице детали акции.
            share.last_price = last_price
            share.is_trend_high = is_trend_high
            share.save(update_fields=["last_price", "is_trend_high", "updated_at"])

        except Exception as e:
            logger.error(e)
