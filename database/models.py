"""Модели базы данных."""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, 
    ForeignKey, JSON, Float, Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class VideoStatus(enum.Enum):
    """Статусы видео."""
    FOUND = "found"
    DOWNLOADED = "downloaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    IN_QUEUE = "in_queue"
    PUBLISHED = "published"
    ERROR = "error"
    BLOCKED = "blocked"


class PlatformType(enum.Enum):
    """Типы платформ."""
    PLATFORM_A = "platform_a"  # TikTok
    PLATFORM_B = "platform_b"  # YouTube Shorts
    PLATFORM_C = "platform_c"  # Instagram Reels


class Topic(Base):
    """Тематика контента."""
    __tablename__ = "topics"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Настройки обработки
    video_speed_change = Column(Float, default=0.0)  # изменение скорости в %
    brightness_adjustment = Column(Float, default=0.0)
    contrast_adjustment = Column(Float, default=0.0)
    crop_settings = Column(JSON, nullable=True)  # {"x": 0, "y": 0, "width": 1080, "height": 1920}
    
    # Брендирование
    branding_enabled = Column(Boolean, default=True)
    branding_logo_path = Column(String(500), nullable=True)
    branding_position = Column(String(50), default="bottom_right")  # top_left, top_right, bottom_left, bottom_right
    branding_size = Column(Integer, default=100)  # размер в пикселях
    branding_opacity = Column(Float, default=0.8)  # 0.0 - 1.0
    branding_margin = Column(Integer, default=20)  # отступ в пикселях
    
    # Описания и теги
    base_tags = Column(JSON, default=list)  # список базовых тегов
    tag_pool = Column(JSON, default=list)  # пул дополнительных тегов
    description_template = Column(Text, nullable=True)  # шаблон описания
    
    # Связи
    accounts = relationship("Account", back_populates="topic")
    sources = relationship("ContentSource", back_populates="topic")
    videos = relationship("Video", back_populates="topic")
    schedules = relationship("Schedule", back_populates="topic")


class Account(Base):
    """Аккаунт на платформе."""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    platform = Column(SQLEnum(PlatformType), nullable=False)
    username = Column(String(200), nullable=False)
    credentials = Column(JSON, nullable=True)  # токены, пароли и т.д.
    # Для Instagram: имя пользователя для сессии (может отличаться от username для публикации)
    instagram_session_username = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    last_check = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    topic = relationship("Topic", back_populates="accounts")
    publications = relationship("Publication", back_populates="account")


class ContentSource(Base):
    """Источник контента."""
    __tablename__ = "content_sources"
    
    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    source_type = Column(String(50), nullable=False)  # profile, hashtag, location, url_list, keywords
    source_value = Column(String(500), nullable=False)  # username, hashtag, location_id, json с URL, ключевые слова
    is_active = Column(Boolean, default=True)
    # Фильтры по метрикам
    min_views = Column(Integer, nullable=True)  # Минимальное количество просмотров
    min_likes = Column(Integer, nullable=True)  # Минимальное количество лайков
    # Instagram аккаунт для сбора (опционально, если не указан - используется дефолтный)
    instagram_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    last_check = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    topic = relationship("Topic", back_populates="sources")
    instagram_account = relationship("Account", foreign_keys=[instagram_account_id])


class Video(Base):
    """Видео контент."""
    __tablename__ = "videos"
    
    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    status = Column(SQLEnum(VideoStatus), default=VideoStatus.FOUND)
    
    # Информация об источнике
    source_url = Column(String(1000), nullable=True)
    source_platform = Column(String(50), nullable=True)  # instagram, tiktok и т.д.
    source_post_id = Column(String(200), nullable=True)
    source_author = Column(String(200), nullable=True)
    
    # Файлы
    original_file_path = Column(String(1000), nullable=True)
    processed_file_path = Column(String(1000), nullable=True)
    
    # Метаданные
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    duration = Column(Float, nullable=True)  # секунды
    resolution = Column(String(50), nullable=True)  # "1080x1920"
    metadata_json = Column(JSON, nullable=True)  # Дополнительные метаданные из источника
    
    # Ошибки
    error_message = Column(Text, nullable=True)
    
    # Временные метки
    found_at = Column(DateTime, default=datetime.utcnow)
    downloaded_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    topic = relationship("Topic", back_populates="videos")
    publications = relationship("Publication", back_populates="video")


class Publication(Base):
    """Публикация видео на платформе."""
    __tablename__ = "publications"
    
    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    platform = Column(SQLEnum(PlatformType), nullable=False)
    
    # Статус публикации
    status = Column(String(50), default="pending")  # pending, published, failed
    platform_post_id = Column(String(200), nullable=True)  # ID поста на платформе
    platform_url = Column(String(1000), nullable=True)  # URL поста
    
    # Метрики
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    last_metrics_update = Column(DateTime, nullable=True)
    
    # Ошибки
    error_message = Column(Text, nullable=True)
    
    # Временные метки
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    video = relationship("Video", back_populates="publications")
    account = relationship("Account", back_populates="publications")


class Schedule(Base):
    """Расписание публикаций."""
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    time_slot = Column(String(10), nullable=False)  # "HH:MM" формат
    day_of_week = Column(Integer, nullable=True)  # 0-6 (понедельник-воскресенье), None = каждый день
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    topic = relationship("Topic", back_populates="schedules")


class DailyReport(Base):
    """Ежедневный отчёт."""
    __tablename__ = "daily_reports"
    
    id = Column(Integer, primary_key=True)
    report_date = Column(DateTime, nullable=False)
    
    # Статистика по тематикам
    topics_stats = Column(JSON, nullable=True)  # {"topic_id": {"found": 10, "published": 5, ...}}
    
    # Общая статистика
    total_found = Column(Integer, default=0)
    total_downloaded = Column(Integer, default=0)
    total_processed = Column(Integer, default=0)
    total_published = Column(Integer, default=0)
    
    # Ошибки
    errors = Column(JSON, default=list)
    warnings = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=datetime.utcnow)
