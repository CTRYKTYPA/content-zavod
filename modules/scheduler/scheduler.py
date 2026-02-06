"""Планировщик публикаций."""
from datetime import datetime, time, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from celery import Celery
from loguru import logger
import pytz

from database.models import Topic, Schedule, Video, VideoStatus, Publication, Account
from modules.content_manager import ContentManager
from modules.publisher import TikTokPublisher, YouTubePublisher, InstagramPublisher
from config import settings

# Создаем Celery приложение
celery_app = Celery('content_zavod', broker=settings.REDIS_URL)


class PublicationScheduler:
    """Планировщик публикаций."""
    
    def __init__(self, db: Session):
        """
        Инициализация планировщика.
        
        Args:
            db: Сессия базы данных
        """
        self.db = db
        self.content_manager = ContentManager(db)
    
    def get_next_publication_time(self, topic_id: int) -> Optional[datetime]:
        """Получить следующее время публикации для тематики."""
        topic = self.content_manager.get_topic(topic_id)
        if not topic:
            return None
        
        schedules = self.db.query(Schedule).filter(
            Schedule.topic_id == topic_id,
            Schedule.is_active == True
        ).all()
        
        if not schedules:
            return None
        
        # Получаем текущее время в часовом поясе тематики
        tz = pytz.timezone(settings.DEFAULT_TIMEZONE)
        now = datetime.now(tz)
        
        # Находим ближайший слот
        next_time = None
        
        for schedule in schedules:
            # Парсим время слота
            hour, minute = map(int, schedule.time_slot.split(':'))
            slot_time = time(hour, minute)
            
            # Проверяем день недели
            if schedule.day_of_week is not None:
                if now.weekday() != schedule.day_of_week:
                    continue
            
            # Создаем datetime для слота сегодня
            slot_datetime = tz.localize(
                datetime.combine(now.date(), slot_time)
            )
            
            # Если слот уже прошел сегодня, берем на завтра
            if slot_datetime <= now:
                slot_datetime += timedelta(days=1)
            
            if next_time is None or slot_datetime < next_time:
                next_time = slot_datetime
        
        return next_time
    
    def get_videos_for_publication(self, topic_id: int, limit: int = 1) -> List[Video]:
        """Получить видео готовые к публикации."""
        videos = self.db.query(Video).filter(
            Video.topic_id == topic_id,
            Video.status == VideoStatus.PROCESSED,
            Video.processed_file_path.isnot(None)
        ).order_by(Video.processed_at.asc()).limit(limit).all()
        
        return videos
    
    def publish_video(self, video_id: int, account_id: int) -> bool:
        """Опубликовать видео через аккаунт."""
        video = self.db.query(Video).filter(Video.id == video_id).first()
        account = self.db.query(Account).filter(Account.id == account_id).first()
        
        if not video or not account:
            return False
        
        if account.topic_id != video.topic_id:
            logger.error(f"Аккаунт {account_id} не принадлежит тематике видео {video_id}")
            return False
        
        # Получаем тематику для шаблона описания
        topic = self.content_manager.get_topic(video.topic_id)
        
        # Формируем описание
        description_template = topic.description_template or "{description}"
        description = self._format_description(description_template, video, topic)
        
        # Формируем теги
        tags = self._get_tags(topic, video)
        
        # Создаем публикатор в зависимости от платформы
        publisher = self._create_publisher(account)
        if not publisher:
            return False
        
        # Публикуем
        success, error_msg, result = publisher.publish(video, description, tags)
        
        if success and result:
            # Создаем запись о публикации
            publication = Publication(
                video_id=video.id,
                account_id=account.id,
                platform=account.platform,
                status="published",
                platform_post_id=result.get("post_id"),
                platform_url=result.get("url"),
                published_at=datetime.utcnow()
            )
            self.db.add(publication)
            
            # Обновляем статус видео
            video.status = VideoStatus.PUBLISHED
            video.published_at = datetime.utcnow()
            
            self.db.commit()
            
            logger.info(f"Видео {video_id} опубликовано на {account.platform.value}")
            return True
        else:
            # Создаем запись об ошибке
            publication = Publication(
                video_id=video.id,
                account_id=account.id,
                platform=account.platform,
                status="failed",
                error_message=error_msg
            )
            self.db.add(publication)
            self.db.commit()
            
            logger.error(f"Ошибка публикации видео {video_id}: {error_msg}")
            return False
    
    def _create_publisher(self, account: Account):
        """Создать публикатор для аккаунта."""
        from database.models import PlatformType
        
        if account.platform == PlatformType.PLATFORM_A:
            return TikTokPublisher(account)
        elif account.platform == PlatformType.PLATFORM_B:
            return YouTubePublisher(account)
        elif account.platform == PlatformType.PLATFORM_C:
            return InstagramPublisher(account)
        return None
    
    def _format_description(self, template: str, video: Video, topic: Topic) -> str:
        """Форматировать описание по шаблону."""
        from datetime import datetime
        
        replacements = {
            "{date}": datetime.now().strftime("%d.%m.%Y"),
            "{topic}": topic.name,
            "{emoji}": "🎬",
            "{cta}": "Подписывайтесь!",
            "{description}": video.description or ""
        }
        
        description = template
        for key, value in replacements.items():
            description = description.replace(key, str(value))
        
        return description
    
    def _get_tags(self, topic: Topic, video: Video) -> List[str]:
        """Получить теги для публикации."""
        import random
        
        tags = list(topic.base_tags or [])
        
        # Добавляем случайные теги из пула
        if topic.tag_pool:
            pool_size = min(5, len(topic.tag_pool))
            random_tags = random.sample(topic.tag_pool, pool_size)
            tags.extend(random_tags)
        
        # Добавляем теги из видео
        if video.tags:
            tags.extend(video.tags[:3])  # Максимум 3 тега из видео
        
        return tags[:10]  # Ограничиваем общее количество


# Celery задачи
@celery_app.task
def process_publication_queue():
    """Обработать очередь публикаций."""
    from database import SessionLocal
    
    db = SessionLocal()
    try:
        scheduler = PublicationScheduler(db)
        
        # Получаем все активные тематики
        topics = db.query(Topic).filter(Topic.is_active == True).all()
        
        for topic in topics:
            # Проверяем, нужно ли публиковать сейчас
            next_time = scheduler.get_next_publication_time(topic.id)
            if not next_time:
                continue
            
            tz = pytz.timezone(settings.DEFAULT_TIMEZONE)
            now = datetime.now(tz)
            
            # Если время публикации наступило
            if now >= next_time:
                # Получаем видео для публикации
                videos = scheduler.get_videos_for_publication(topic.id, limit=1)
                
                if not videos:
                    logger.warning(f"Нет видео для публикации в тематике {topic.id}")
                    continue
                
                # Получаем аккаунты тематики
                accounts = scheduler.content_manager.get_accounts_by_topic(topic.id)
                
                for video in videos:
                    for account in accounts:
                        if account.is_active:
                            scheduler.publish_video(video.id, account.id)
                            break  # Публикуем только на один аккаунт за раз
    
    finally:
        db.close()


@celery_app.task
def collect_content_task():
    """Задача сбора контента."""
    from database import SessionLocal
    
    db = SessionLocal()
    try:
        manager = ContentManager(db)
        
        # Получаем все активные источники
        sources = db.query(ContentSource).filter(ContentSource.is_active == True).all()
        
        for source in sources:
            try:
                manager.collect_content_from_source(source.id, limit=10)
            except Exception as e:
                logger.error(f"Ошибка сбора из источника {source.id}: {e}")
    
    finally:
        db.close()
