"""Скрипт для инициализации базы данных."""
from database import init_db
from loguru import logger

if __name__ == "__main__":
    logger.info("Инициализация базы данных...")
    init_db()
    logger.info("База данных инициализирована успешно!")
