"""Модуль базы данных."""
from .models import (
    Base, Topic, Account, ContentSource, Video, 
    Publication, Schedule, DailyReport,
    VideoStatus, PlatformType
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config import settings
from typing import Generator

# Создаем движок БД
# Для SQLite добавляем connect_args для поддержки внешних ключей
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Получить сессию БД."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Инициализировать базу данных (создать таблицы)."""
    Base.metadata.create_all(bind=engine)
