"""Главный файл запуска системы."""
from pathlib import Path
from loguru import logger
from database import init_db, get_db
from config import settings
from modules.telegram_bot import TelegramBot
from modules.analytics import Analytics
from modules.scheduler import celery_app, collect_content_task, process_publication_queue
from celery.schedules import crontab

# Настройка логирования
logger.add(
    settings.LOGS_DIR / "content_zavod_{time}.log",
    rotation="1 day",
    retention="30 days",
    level=settings.LOG_LEVEL
)


def setup_celery():
    """Настроить Celery задачи."""
    # Периодические задачи
    celery_app.conf.beat_schedule = {
        'collect-content': {
            'task': 'modules.scheduler.scheduler.collect_content_task',
            'schedule': crontab(minute='*/30'),  # Каждые 30 минут
        },
        'process-publications': {
            'task': 'modules.scheduler.scheduler.process_publication_queue',
            'schedule': crontab(minute='*/5'),  # Каждые 5 минут
        },
    }
    celery_app.conf.timezone = settings.DEFAULT_TIMEZONE


def main():
    """Главная функция запуска."""
    logger.info("Запуск системы управления контентом...")
    
    # Инициализация БД
    logger.info("Инициализация базы данных...")
    init_db()
    
    # Настройка Celery
    logger.info("Настройка Celery...")
    setup_celery()
    
    # Запуск Telegram-бота
    logger.info("Запуск Telegram-бота...")
    db_session = next(get_db())
    bot = TelegramBot(db_session)
    
    # Запускаем бота в отдельном потоке
    import threading
    bot_thread = threading.Thread(target=bot.run, daemon=True)
    bot_thread.start()
    
    logger.info("Система запущена. Telegram-бот работает.")
    logger.info("Для остановки нажмите Ctrl+C")
    
    # Держим программу запущенной
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Остановка системы...")


if __name__ == "__main__":
    main()
