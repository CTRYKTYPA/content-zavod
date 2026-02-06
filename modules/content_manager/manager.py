"""Менеджер контента и тематик."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from loguru import logger

from database.models import (
    Topic, Account, ContentSource, Video, Schedule,
    VideoStatus, PlatformType
)
from modules.content_collector import InstagramCollector
from modules.content_collector.tiktok_collector import TikTokCollector
from modules.content_collector.youtube_collector import YouTubeShortsCollector
from modules.video_processor import VideoProcessor
from config import settings


class ContentManager:
    """Менеджер для управления тематиками, источниками и контентом."""
    
    def __init__(self, db: Session):
        """
        Инициализация менеджера.
        
        Args:
            db: Сессия базы данных
        """
        self.db = db
    
    # ========== Управление тематиками ==========
    
    def create_topic(
        self,
        name: str,
        description: Optional[str] = None,
        **kwargs
    ) -> Topic:
        """Создать новую тематику."""
        topic = Topic(
            name=name,
            description=description,
            **kwargs
        )
        self.db.add(topic)
        self.db.commit()
        self.db.refresh(topic)
        logger.info(f"Создана тематика: {name}")
        return topic
    
    def get_topic(self, topic_id: int) -> Optional[Topic]:
        """Получить тематику по ID."""
        return self.db.query(Topic).filter(Topic.id == topic_id).first()
    
    def get_all_topics(self, active_only: bool = False) -> List[Topic]:
        """Получить все тематики."""
        query = self.db.query(Topic)
        if active_only:
            query = query.filter(Topic.is_active == True)
        return query.all()
    
    def update_topic(self, topic_id: int, **kwargs) -> Optional[Topic]:
        """Обновить тематику."""
        topic = self.get_topic(topic_id)
        if not topic:
            return None
        
        for key, value in kwargs.items():
            if hasattr(topic, key):
                setattr(topic, key, value)
        
        topic.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(topic)
        return topic
    
    def delete_topic(self, topic_id: int) -> bool:
        """Удалить тематику."""
        topic = self.get_topic(topic_id)
        if not topic:
            return False
        
        self.db.delete(topic)
        self.db.commit()
        return True
    
    # ========== Управление аккаунтами ==========
    
    def add_account(
        self,
        topic_id: int,
        platform: PlatformType,
        username: str,
        credentials: Optional[Dict[str, Any]] = None
    ) -> Account:
        """Добавить аккаунт к тематике."""
        account = Account(
            topic_id=topic_id,
            platform=platform,
            username=username,
            credentials=credentials or {}
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        logger.info(f"Добавлен аккаунт {username} на {platform.value} к тематике {topic_id}")
        return account
    
    def get_accounts_by_topic(self, topic_id: int, active_only: bool = True) -> List[Account]:
        """Получить аккаунты тематики."""
        query = self.db.query(Account).filter(Account.topic_id == topic_id)
        if active_only:
            query = query.filter(Account.is_active == True)
        return query.all()
    
    def update_account(self, account_id: int, **kwargs) -> Optional[Account]:
        """Обновить аккаунт."""
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return None
        
        for key, value in kwargs.items():
            if hasattr(account, key):
                setattr(account, key, value)
        
        account.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(account)
        return account
    
    # ========== Управление источниками ==========
    
    def add_source(
        self,
        topic_id: int,
        source_type: str,
        source_value: str,
        min_views: Optional[int] = None,
        min_likes: Optional[int] = None
    ) -> ContentSource:
        """Добавить источник контента."""
        source = ContentSource(
            topic_id=topic_id,
            source_type=source_type,
            source_value=source_value,
            min_views=min_views,
            min_likes=min_likes
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        logger.info(f"Добавлен источник {source_type}: {source_value} к тематике {topic_id}")
        return source
    
    def get_sources_by_topic(self, topic_id: int, active_only: bool = True) -> List[ContentSource]:
        """Получить источники тематики."""
        query = self.db.query(ContentSource).filter(ContentSource.topic_id == topic_id)
        if active_only:
            query = query.filter(ContentSource.is_active == True)
        return query.all()
    
    def collect_content_from_source(self, source_id: int, limit: Optional[int] = None) -> List[Video]:
        """
        Собрать контент из источника.
        
        Args:
            source_id: ID источника
            limit: Максимальное количество видео
            
        Returns:
            Список созданных видео
        """
        source = self.db.query(ContentSource).filter(ContentSource.id == source_id).first()
        if not source or not source.is_active:
            return []
        
        collector = None
        platform = "instagram"
        if source.source_type in ["profile", "hashtag", "reels", "url_list", "keywords"]:
            collector = InstagramCollector(source)
        elif source.source_type == "youtube_shorts":
            proxy = getattr(settings, "YOUTUBE_PROXY", None) or settings.INSTAGRAM_PROXY
            collector = YouTubeShortsCollector(source, proxy=proxy)
            platform = "youtube"
        elif source.source_type == "tiktok":
            proxy = getattr(settings, "TIKTOK_PROXY", None) or getattr(settings, "YOUTUBE_PROXY", None) or settings.INSTAGRAM_PROXY
            collector = TikTokCollector(source, proxy=proxy)
            platform = "tiktok"
        else:
            logger.warning(f"Неподдерживаемый тип источника: {source.source_type}")
            return []

        exclude_ids: set[str] = set()
        if platform in ("youtube", "tiktok"):
            rows = self.db.query(Video.source_post_id).filter(
                Video.topic_id == source.topic_id,
                Video.source_post_id.isnot(None),
            ).all()
            exclude_ids = {r[0] for r in rows if r[0]}

        if platform in ("youtube", "tiktok") and exclude_ids:
            videos_info = collector.collect_videos(limit=limit, exclude_source_ids=exclude_ids)
        else:
            videos_info = collector.collect_videos(limit=limit)
        created_videos = []

        min_views = source.min_views
        min_likes = source.min_likes
        quick_demo = os.environ.get("STAGE1_QUICK") == "1" and (limit or 0) <= 6
        if platform in ("youtube", "tiktok"):
            if quick_demo:
                min_views = 0
                min_likes = 0
            else:
                min_views = min_views or 0
                min_likes = min_likes if min_likes is not None else 10000
        else:
            min_views = min_views or 1_000_000
            min_likes = min_likes if min_likes is not None else 10000

        for video_info in videos_info:
            is_valid, error_msg = collector.validate_video(
                video_info, min_views=min_views, min_likes=min_likes
            )
            if not is_valid:
                logger.debug(f"Видео не прошло валидацию: {error_msg}")
                continue

            existing = self.db.query(Video).filter(
                Video.source_post_id == video_info["source_post_id"],
                Video.topic_id == source.topic_id,
            ).first()
            if existing:
                continue

            video = Video(
                topic_id=source.topic_id,
                status=VideoStatus.FOUND,
                source_url=video_info["source_url"],
                source_platform=platform,
                source_post_id=video_info["source_post_id"],
                source_author=video_info["source_author"],
                title=video_info.get("title"),
                description=video_info.get("description"),
                tags=video_info.get("tags", []),
                duration=video_info.get("duration"),
                metadata_json=video_info.get("metadata", {}),
            )
            self.db.add(video)
            created_videos.append(video)
        
        self.db.commit()
        
        # Обновляем время последней проверки источника
        source.last_check = datetime.utcnow()
        self.db.commit()
        
        return created_videos
    
    def download_video(self, video_id: int) -> bool:
        """Скачать видео."""
        video = self.db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return False
        
        if video.status != VideoStatus.FOUND:
            logger.warning(f"Видео {video_id} уже скачано или в другом статусе")
            return False
        
        q = self.db.query(ContentSource).filter(
            ContentSource.topic_id == video.topic_id,
            ContentSource.is_active == True,
        )
        if getattr(video, "source_platform", None) == "youtube":
            q = q.filter(ContentSource.source_type == "youtube_shorts")
        elif getattr(video, "source_platform", None) == "tiktok":
            q = q.filter(ContentSource.source_type == "tiktok")
        else:
            q = q.filter(ContentSource.source_type.in_(
                ["profile", "hashtag", "reels", "url_list", "keywords"]
            ))
        source = q.first()
        if not source:
            return False

        if source.source_type == "youtube_shorts":
            proxy = getattr(settings, "YOUTUBE_PROXY", None) or settings.INSTAGRAM_PROXY
            collector = YouTubeShortsCollector(source, proxy=proxy)
        elif source.source_type == "tiktok":
            proxy = getattr(settings, "TIKTOK_PROXY", None) or getattr(settings, "YOUTUBE_PROXY", None) or settings.INSTAGRAM_PROXY
            collector = TikTokCollector(source, proxy=proxy)
        else:
            collector = InstagramCollector(source)

        filename = f"{video.source_post_id}.mp4"
        download_path = settings.DOWNLOADS_DIR / str(video.topic_id) / filename

        video.status = VideoStatus.DOWNLOADED
        video.original_file_path = str(download_path)

        if collector.download_video(video.source_url, str(download_path)):
            video.downloaded_at = datetime.utcnow()
            self.db.commit()
            return True
        else:
            video.status = VideoStatus.ERROR
            video.error_message = "Ошибка скачивания"
            self.db.commit()
            return False
    
    def process_video(self, video_id: int) -> bool:
        """Обработать видео."""
        video = self.db.query(Video).filter(Video.id == video_id).first()
        if not video or not video.original_file_path:
            return False
        
        if video.status != VideoStatus.DOWNLOADED:
            logger.warning(f"Видео {video_id} не готово к обработке")
            return False
        
        # Получаем тематику
        topic = self.get_topic(video.topic_id)
        if not topic:
            return False
        
        # Создаем процессор
        processor = VideoProcessor(topic)
        
        # Формируем путь для обработанного видео
        filename = f"{video.source_post_id}_processed.mp4"
        processed_path = settings.PROCESSED_DIR / str(video.topic_id) / filename
        
        # Обрабатываем
        video.status = VideoStatus.PROCESSING
        self.db.commit()
        
        success, error_msg = processor.process_video(
            video.original_file_path,
            str(processed_path)
        )
        
        if success:
            video.status = VideoStatus.PROCESSED
            video.processed_file_path = str(processed_path)
            video.processed_at = datetime.utcnow()
            
            # Получаем информацию о видео
            info = processor.get_video_info(str(processed_path))
            video.duration = info.get("duration")
            video.resolution = info.get("resolution")
            
            self.db.commit()
            return True
        else:
            video.status = VideoStatus.ERROR
            video.error_message = error_msg or "Ошибка обработки"
            self.db.commit()
            return False
