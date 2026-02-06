"""Скрипт для отправки ежедневного отчёта через Telegram."""
from datetime import datetime
from loguru import logger
from database import get_db
from modules.analytics import Analytics
from modules.telegram_bot import TelegramBot
from config import settings

def send_daily_report():
    """Отправить ежедневный отчёт."""
    db = next(get_db())
    
    try:
        analytics = Analytics(db)
        
        # Генерируем отчёт за вчера
        yesterday = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        report = analytics.generate_daily_report(yesterday)
        
        # Форматируем отчёт
        report_text = analytics.format_report_text(report)
        
        # Отправляем через Telegram
        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ADMIN_IDS:
            bot = TelegramBot(db)
            for admin_id in settings.TELEGRAM_ADMIN_IDS:
                try:
                    bot.application.bot.send_message(
                        chat_id=admin_id,
                        text=report_text
                    )
                    logger.info(f"Отчёт отправлен администратору {admin_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки отчёта администратору {admin_id}: {e}")
        else:
            logger.warning("Telegram Bot Token или Admin IDs не настроены")
            print(report_text)
    
    finally:
        db.close()

if __name__ == "__main__":
    send_daily_report()
