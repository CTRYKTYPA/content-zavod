"""Отправка отчётов в Telegram админам (без запуска бота)."""
from __future__ import annotations

import requests

from config import settings


def send_report_to_admins(text: str) -> None:
    """
    Отправить сообщение всем TELEGRAM_ADMIN_IDS.
    Токен и админы из .env. Бот может не быть запущен — используем API напрямую.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    admin_ids = getattr(settings, "TELEGRAM_ADMIN_IDS", None) or []
    if not token or not admin_ids:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id in admin_ids:
        try:
            requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        except Exception:
            pass
