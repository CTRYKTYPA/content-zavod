"""Публикатор для YouTube Shorts."""
from typing import Optional, Dict, Any
from loguru import logger
from .base_publisher import BasePublisher
from database.models import Video


class YouTubePublisher(BasePublisher):
    """Публикатор для YouTube Shorts."""
    
    def publish(self, video: Video, description: str, tags: list[str]) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Опубликовать видео на YouTube Shorts.
        
        Требуется настроенный Google API Client с OAuth2.
        """
        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
            
            # Загружаем credentials из аккаунта
            creds_data = self.credentials.get("credentials")
            if not creds_data:
                return False, "Отсутствуют credentials для YouTube API", None
            
            # Создаем credentials объект
            creds = Credentials.from_authorized_user_info(creds_data)
            youtube = build('youtube', 'v3', credentials=creds)
            
            # Подготавливаем описание с тегами
            full_description = description
            if tags:
                full_description += "\n\n" + " ".join([f"#{tag}" for tag in tags])
            
            # Загружаем видео
            body = {
                'snippet': {
                    'title': video.title or 'Short Video',
                    'description': full_description,
                    'tags': tags,
                    'categoryId': '24'  # Entertainment
                },
                'status': {
                    'privacyStatus': 'public',
                    'madeForKids': False
                }
            }
            
            # Запрос на загрузку
            insert_request = youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=video.processed_file_path
            )
            
            response = insert_request.execute()
            
            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            logger.info(f"Видео опубликовано на YouTube: {video_url}")
            
            return True, None, {
                "post_id": video_id,
                "url": video_url
            }
        
        except Exception as e:
            logger.error(f"Ошибка публикации на YouTube: {e}")
            return False, str(e), None
    
    def get_metrics(self, post_id: str) -> Dict[str, Any]:
        """Получить метрики видео YouTube."""
        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
            
            creds_data = self.credentials.get("credentials")
            if not creds_data:
                return {}
            
            creds = Credentials.from_authorized_user_info(creds_data)
            youtube = build('youtube', 'v3', credentials=creds)
            
            request = youtube.videos().list(
                part='statistics',
                id=post_id
            )
            response = request.execute()
            
            if not response.get('items'):
                return {}
            
            stats = response['items'][0]['statistics']
            
            return {
                "views": int(stats.get('viewCount', 0)),
                "likes": int(stats.get('likeCount', 0)),
                "comments": int(stats.get('commentCount', 0)),
                "shares": 0  # YouTube API не предоставляет shares напрямую
            }
        
        except Exception as e:
            logger.error(f"Ошибка получения метрик YouTube: {e}")
            return {}
