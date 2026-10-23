from decimal import Decimal

from config.settings import TINKOFF_TOKEN, logger


def get_last_data(share):
    from tinkoff.invest import Client

    with Client(TINKOFF_TOKEN) as client:
        resp = client.market_data.get_last_prices(figi=[share.figi])
        if not resp.last_prices:
            raise ValueError(f"No market price returned for share {share.id}")
        resp = resp.last_prices[0]
        logger.info(f"Get last data for share with id {share.id}")
        price = Decimal(resp.price.units) + Decimal(resp.price.nano) / Decimal(
            1_000_000_000
        )
        return price, resp.time
