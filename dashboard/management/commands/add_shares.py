from django.core.management.base import BaseCommand, CommandError

from dashboard.models import Share
from dashboard.services.tinkoff_client import (
    MarketDataUnavailable,
    get_client,
    is_available,
)


class Command(BaseCommand):
    help = "Add shares to DB"

    def handle(self, *args, **options):
        if not is_available():
            raise CommandError(
                "Tinkoff Invest API недоступен: установите пакет tinkoff "
                "и задайте переменную окружения TINKOFF_TOKEN."
            )

        try:
            with get_client() as client:
                shares = client.instruments.shares()
                created = 0
                updated = 0
                for share in shares.instruments:
                    obj, was_created = Share.objects.update_or_create(
                        figi=share.figi,
                        defaults={
                            "name": share.name,
                            "isin": share.isin,
                            "ticker": share.ticker,
                            "currency": share.currency,
                            "uid": share.uid,
                        },
                    )
                    if was_created:
                        created += 1
                    else:
                        updated += 1
        except MarketDataUnavailable as exc:
            raise CommandError(str(exc))

        self.stdout.write(
            self.style.SUCCESS(f"Создано: {created}, обновлено: {updated}")
        )
