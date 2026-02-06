"""Базовый класс для публикации на платформы."""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from database.models import Account, Video, PlatformType


class BasePublisher(ABC):
    """Базовый класс для всех публикаторов."""
    
    def __init__(self, account: Account):
        """
        Инициализация публикатора.
        
        Args:
            account: Аккаунт на платформе
        """
        self.account = account
        self.platform = account.platform
        self.credentials = account.credentials or {}
    
    @abstractmethod
    def publish(self, video: Video, description: str, tags: list[str]) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Опубликовать видео.
        
        Args:
            video: Видео для публикации
            description: Описание
            tags: Теги
            
        Returns:
            (success, error_message, result_data)
            result_data может содержать: {"post_id": str, "url": str}
        """
        pass
    
    @abstractmethod
    def get_metrics(self, post_id: str) -> Dict[str, Any]:
        """
        Получить метрики поста.
        
        Args:
            post_id: ID поста на платформе
            
        Returns:
            Словарь с метриками: {"views": int, "likes": int, "comments": int, "shares": int}
        """
        pass
    
    def format_description(self, template: str, video: Video, **kwargs) -> str:
        """Форматировать описание по шаблону."""
        from datetime import datetime
        
        replacements = {
            "{date}": datetime.now().strftime("%d.%m.%Y"),
            "{topic}": video.topic.name if video.topic else "",
            "{emoji}": "🎬",
            "{cta}": "Подписывайтесь!",
            **kwargs
        }
        
        description = template
        for key, value in replacements.items():
            description = description.replace(key, str(value))
        
        return description
