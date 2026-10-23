import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0007_add_updated_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "price",
                    models.DecimalField(decimal_places=9, max_digits=20),
                ),
                (
                    "recorded_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "share",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_history",
                        to="dashboard.share",
                    ),
                ),
            ],
            options={
                "ordering": ["recorded_at"],
            },
        ),
        migrations.AddIndex(
            model_name="pricehistory",
            index=models.Index(
                fields=["share", "recorded_at"],
                name="dashboard_p_share_i_db00cd_idx",
            ),
        ),
    ]
