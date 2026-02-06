"""
Модуль для сбора видео по теме "Бизнес".
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger
from datetime import datetime
from sqlalchemy.orm import Session

from database.models import Topic, Video, VideoStatus
from modules.content_collector.instagram_video_finder import InstagramVideoFinder
from modules.content_collector.instagram_downloader import extract_shortcode
from modules.content_collector.instagram_downloader import download_video_combined


class BusinessCollector:
    """Сборщик видео по теме Бизнес."""
    
    THEME_NAME = "Бизнес"
    THEME_FOLDER = "business"
    
    HASHTAGS = [
        "business", "entrepreneur", "startup", "success", "motivation",
        "businessideas", "entrepreneurship", "businessmindset", "successmindset", "businessgrowth"
    ]
    
    MIN_VIEWS = 300000  # 300к просмотров
    MIN_LIKES = 3000    # 3к лайков
    
    def __init__(self, db: Session, topic: Topic):
        self.db = db
        self.topic = topic
        self.finder = InstagramVideoFinder()
        self.theme_folder = Path("downloads") / self.THEME_FOLDER
        self.theme_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Инициализирован сборщик для темы: {self.THEME_NAME}")
    
    def find_videos_by_hashtags(self, limit_per_hashtag: int = 5) -> List[str]:
        all_video_urls = []
        logger.info(f"Ищу видео по хэштегам темы '{self.THEME_NAME}'...")
        
        for hashtag in self.HASHTAGS:
            try:
                logger.info(f"Поиск по хэштегу #{hashtag}...")
                video_urls = self.finder.find_videos_from_hashtag(hashtag, limit_per_hashtag)
                all_video_urls.extend(video_urls)
            except Exception as e:
                logger.error(f"Ошибка поиска по #{hashtag}: {e}")
                continue
        
        unique_urls = list(set(all_video_urls))
        logger.info(f"Всего найдено уникальных видео: {len(unique_urls)}")
        return unique_urls
    
    def save_to_database(self, video_url: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[Video]:
        try:
            shortcode = extract_shortcode(video_url)
            if not shortcode:
                return None
            
            existing = self.db.query(Video).filter(
                Video.source_post_id == shortcode,
                Video.topic_id == self.topic.id
            ).first()
            
            if existing:
                return existing
            
            video = Video(
                topic_id=self.topic.id,
                status=VideoStatus.FOUND,
                source_url=video_url,
                source_platform="instagram",
                source_post_id=shortcode,
                source_author=metadata.get("author") if metadata else None,
                title=metadata.get("title") if metadata else None,
                description=metadata.get("description") if metadata else None,
                tags=metadata.get("tags", []) if metadata else [],
                duration=metadata.get("duration") if metadata else None,
                metadata_json=metadata or {}
            )
            
            self.db.add(video)
            self.db.commit()
            self.db.refresh(video)
            logger.info(f"Видео {shortcode} сохранено в БД (ID: {video.id})")
            return video
        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}")
            self.db.rollback()
            return None
    
    def download_video(self, video_url: str, video_db: Video) -> bool:
        try:
            shortcode = extract_shortcode(video_url) or f"video_{video_db.id}"
            output_path = self.theme_folder / f"{shortcode}.mp4"
            
            success = download_video_combined(video_url, str(output_path))
            
            if success and output_path.exists():
                video_db.original_file_path = str(output_path)
                video_db.status = VideoStatus.DOWNLOADED
                video_db.downloaded_at = datetime.utcnow()
                self.db.commit()
                logger.info(f"Видео скачано: {output_path}")
                return True
            else:
                video_db.status = VideoStatus.ERROR
                video_db.error_message = "Не удалось скачать видео"
                self.db.commit()
                return False
        except Exception as e:
            logger.error(f"Ошибка скачивания: {e}")
            if video_db:
                video_db.status = VideoStatus.ERROR
                video_db.error_message = str(e)
                self.db.commit()
            return False
    
    def collect_and_download(self, limit: int = 10, download: bool = True) -> Dict[str, Any]:
        logger.info(f"Начинаю сбор видео для темы '{self.THEME_NAME}'...")
        
        video_urls = self.find_videos_by_hashtags(limit_per_hashtag=limit // len(self.HASHTAGS) + 1)
        video_urls = video_urls[:limit]
        
        saved_count = 0
        downloaded_count = 0
        failed_count = 0
        
        for i, video_url in enumerate(video_urls, 1):
            logger.info(f"\n[{i}/{len(video_urls)}] Обрабатываю: {video_url}")
            
            video_db = self.save_to_database(video_url)
            if not video_db:
                failed_count += 1
                continue
            
            saved_count += 1
            
            if download:
                if self.download_video(video_url, video_db):
                    downloaded_count += 1
                else:
                    failed_count += 1
        
        result = {
            'found': len(video_urls),
            'saved_to_db': saved_count,
            'downloaded': downloaded_count,
            'failed': failed_count,
            'theme': self.THEME_NAME
        }
        
        logger.info(f"\n{'='*70}")
        logger.info(f"СБОР ЗАВЕРШЕН для темы '{self.THEME_NAME}'")
        logger.info(f"Найдено: {result['found']}, Сохранено: {result['saved_to_db']}, Скачано: {result['downloaded']}")
        logger.info(f"{'='*70}")
        
        return result
