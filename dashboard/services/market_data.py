"""
Получение рыночных данных для акции.

Делегирует работу с Tinkoff API модулю ``tinkoff_client``. Если библиотека
не установлена — возвращает синтетические данные (см. ``tinkoff_client``).
"""
from dashboard.services.tinkoff_client import get_last_data

__all__ = ["get_last_data"]
