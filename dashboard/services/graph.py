from datetime import timedelta

from django.utils import timezone
from plotly.graph_objs import Scatter
from plotly.offline import plot

from dashboard.models import PriceHistory


def get_graph(share, days=180):
    history = PriceHistory.objects.filter(
        share=share, recorded_at__gte=timezone.now() - timedelta(days=days)
    ).order_by("recorded_at")
    x_data = [item.recorded_at for item in history]
    y_data = [float(item.price) for item in history]
    plot_div = plot(
        [
            Scatter(
                x=x_data,
                y=y_data,
                mode="lines",
                name="price",
                opacity=0.8,
                marker_color="red",
            )
        ],
        output_type="div",
        show_link=False,
        link_text="",
    )
    return plot_div
