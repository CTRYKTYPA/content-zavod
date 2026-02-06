"""Базовый класс для сборщиков контента."""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
from database.models import VideoStatus, ContentSource


class BaseCollector(ABC):
    """Базовый класс для всех сборщиков контента."""
    
    def __init__(self, source: ContentSource):
        """
        Инициализация сборщика.
        
        Args:
            source: Источник контента из БД
        """
        self.source = source
        self.source_type = source.source_type
        self.source_value = source.source_value
    
    @abstractmethod
    def collect_videos(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Собрать видео из источника.
        
        Args:
            limit: Максимальное количество видео для сбора
            
        Returns:
            Список словарей с информацией о видео:
            {
                "source_url": str,
                "source_post_id": str,
                "source_author": str,
                "title": str,
                "description": str,
                "tags": List[str],
                "duration": float,
                "video_url": str,
                "thumbnail_url": Optional[str],
                "metadata": Dict[str, Any]
            }
        """
        pass
    
    @abstractmethod
    def download_video(self, video_url: str, output_path: str) -> bool:
        """
        Скачать видео по URL.
        
        Args:
            video_url: URL видео
            output_path: Путь для сохранения
            
        Returns:
            True если успешно, False иначе
        """
        pass
    
    def validate_video(
        self, 
        video_info: Dict[str, Any],
        min_views: Optional[int] = None,
        min_likes: Optional[int] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Валидация видео перед добавлением в систему.
        
        Args:
            video_info: Информация о видео
            min_views: Минимальное количество просмотров (опционально)
            min_likes: Минимальное количество лайков (опционально)
            
        Returns:
            (is_valid, error_message)
        """
        # Проверка наличия URL
        if not video_info.get("video_url"):
            return False, "Отсутствует URL видео"
        
        # Проверка метрик (просмотры ИЛИ лайки - достаточно одного условия)
        metadata = video_info.get("metadata", {})
        views = metadata.get("view_count") or metadata.get("views") or 0
        likes = metadata.get("likes") or 0
        
        # Если указаны оба фильтра, проверяем что хотя бы одно условие выполнено
        if min_views is not None and min_likes is not None:
            if views < min_views and likes < min_likes:
                return False, f"Недостаточно просмотров ({views} < {min_views}) и лайков ({likes} < {min_likes})"
        elif min_views is not None:
            if views < min_views:
                return False, f"Недостаточно просмотров: {views} < {min_views}"
        elif min_likes is not None:
            if likes < min_likes:
                return False, f"Недостаточно лайков: {likes} < {min_likes}"
        
        return True, None
