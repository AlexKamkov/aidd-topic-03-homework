"""
Построение графика исторических цен акции.

Данные берутся через ``tinkoff_client``, который корректно деградирует при
недоступности библиотеки ``tinkoff``.
"""
from plotly.graph_objs import Scatter
from plotly.offline import plot

from config.settings import logger
from dashboard.services.tinkoff_client import MarketDataUnavailable, get_candles


def get_graph(share, days=180):
    """Возвращает HTML-блок с графиком цены акции за *days* дней."""
    try:
        candles = get_candles(share, days=days)
    except MarketDataUnavailable as exc:
        # Раньше любая ошибка внешнего API приводила к 500 на странице акции.
        logger.error(f"Graph data unavailable for share id={share.id}: {exc}")
        candles = []

    if not candles:
        return (
            "<p>Исторические данные недоступны: внешний рынок котировок "
            "недоступен или по акции нет наблюдений.</p>"
        )

    x_data, y_data = zip(*candles)

    plot_div = plot(
        [
            Scatter(
                x=list(x_data),
                y=list(y_data),
                mode="lines",
                name=share.ticker or share.name,
                opacity=0.8,
                marker_color="red",
            )
        ],
        output_type="div",
        # base.html уже подключает plotly.js с CDN, поэтому встроенный бандл
        # (~3.5 МБ на каждую страницу) не нужен.
        include_plotlyjs=False,
    )
    return plot_div
