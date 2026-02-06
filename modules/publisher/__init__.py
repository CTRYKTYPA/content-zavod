"""Модуль публикации на платформы."""
from .base_publisher import BasePublisher
from .tiktok_publisher import TikTokPublisher
from .youtube_publisher import YouTubePublisher
from .instagram_publisher import InstagramPublisher

__all__ = [
    "BasePublisher",
    "TikTokPublisher", 
    "YouTubePublisher",
    "InstagramPublisher"
]
