"""Модуль сбора контента."""
from .base_collector import BaseCollector
from .instagram_collector import InstagramCollector
from .tiktok_collector import TikTokCollector
from .youtube_collector import YouTubeShortsCollector

__all__ = ["BaseCollector", "InstagramCollector", "TikTokCollector", "YouTubeShortsCollector"]
