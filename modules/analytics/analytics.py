"""Модуль аналитики и отчетности."""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from loguru import logger

from database.models import (
    Topic, Video, VideoStatus, Publication, DailyReport, Account, Schedule
)
from modules.publisher import TikTokPublisher, YouTubePublisher, InstagramPublisher


class Analytics:
    """Аналитика и отчетность."""
    
    def __init__(self, db: Session):
        """
        Инициализация аналитики.
        
        Args:
            db: Сессия базы данных
        """
        self.db = db
    
    def generate_daily_report(self, report_date: Optional[datetime] = None) -> DailyReport:
        """
        Сгенерировать ежедневный отчёт.
        
        Args:
            report_date: Дата отчёта (по умолчанию сегодня)
            
        Returns:
            Объект DailyReport
        """
        if report_date is None:
            report_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Проверяем, не существует ли уже отчёт за эту дату
        existing = self.db.query(DailyReport).filter(
            func.date(DailyReport.report_date) == report_date.date()
        ).first()
        
        if existing:
            return existing
        
        # Статистика по тематикам
        topics_stats = {}
        topics = self.db.query(Topic).all()
        
        for topic in topics:
            stats = self._get_topic_stats(topic.id, report_date)
            topics_stats[topic.id] = stats
        
        # Общая статистика
        total_found = self.db.query(func.count(Video.id)).filter(
            func.date(Video.found_at) == report_date.date()
        ).scalar() or 0
        
        total_downloaded = self.db.query(func.count(Video.id)).filter(
            func.date(Video.downloaded_at) == report_date.date()
        ).scalar() or 0
        
        total_processed = self.db.query(func.count(Video.id)).filter(
            func.date(Video.processed_at) == report_date.date()
        ).scalar() or 0
        
        total_published = self.db.query(func.count(Publication.id)).filter(
            func.date(Publication.published_at) == report_date.date(),
            Publication.status == "published"
        ).scalar() or 0
        
        # Ошибки и предупреждения
        errors = self._get_errors(report_date)
        warnings = self._get_warnings(report_date)
        
        # Создаем отчёт
        report = DailyReport(
            report_date=report_date,
            topics_stats=topics_stats,
            total_found=total_found,
            total_downloaded=total_downloaded,
            total_processed=total_processed,
            total_published=total_published,
            errors=errors,
            warnings=warnings
        )
        
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        
        logger.info(f"Сгенерирован ежедневный отчёт за {report_date.date()}")
        return report
    
    def _get_topic_stats(self, topic_id: int, report_date: datetime) -> Dict[str, Any]:
        """Получить статистику по тематике."""
        found = self.db.query(func.count(Video.id)).filter(
            Video.topic_id == topic_id,
            func.date(Video.found_at) == report_date.date()
        ).scalar() or 0
        
        downloaded = self.db.query(func.count(Video.id)).filter(
            Video.topic_id == topic_id,
            func.date(Video.downloaded_at) == report_date.date()
        ).scalar() or 0
        
        processed = self.db.query(func.count(Video.id)).filter(
            Video.topic_id == topic_id,
            func.date(Video.processed_at) == report_date.date()
        ).scalar() or 0
        
        published = self.db.query(func.count(Publication.id)).join(Video).filter(
            Video.topic_id == topic_id,
            func.date(Publication.published_at) == report_date.date(),
            Publication.status == "published"
        ).scalar() or 0
        
        return {
            "found": found,
            "downloaded": downloaded,
            "processed": processed,
            "published": published
        }
    
    def _get_errors(self, report_date: datetime) -> List[Dict[str, Any]]:
        """Получить список ошибок за день."""
        errors = []
        
        # Ошибки видео
        error_videos = self.db.query(Video).filter(
            Video.status == VideoStatus.ERROR,
            func.date(Video.updated_at) == report_date.date()
        ).all()
        
        for video in error_videos:
            errors.append({
                "type": "video_error",
                "video_id": video.id,
                "message": video.error_message,
                "timestamp": video.updated_at.isoformat()
            })
        
        # Ошибки публикаций
        failed_publications = self.db.query(Publication).filter(
            Publication.status == "failed",
            func.date(Publication.updated_at) == report_date.date()
        ).all()
        
        for pub in failed_publications:
            errors.append({
                "type": "publication_error",
                "publication_id": pub.id,
                "video_id": pub.video_id,
                "platform": pub.platform.value,
                "message": pub.error_message,
                "timestamp": pub.updated_at.isoformat()
            })
        
        return errors
    
    def _get_warnings(self, report_date: datetime) -> List[Dict[str, Any]]:
        """Получить предупреждения за день."""
        warnings = []
        
        # Проверяем нехватку контента
        topics = self.db.query(Topic).filter(Topic.is_active == True).all()
        
        for topic in topics:
            # Количество готовых к публикации видео
            ready_videos = self.db.query(func.count(Video.id)).filter(
                Video.topic_id == topic.id,
                Video.status == VideoStatus.PROCESSED
            ).scalar() or 0
            
            # Количество запланированных публикаций на завтра
            tomorrow = report_date + timedelta(days=1)
            schedules = self.db.query(Schedule).filter(
                Schedule.topic_id == topic.id,
                Schedule.is_active == True
            ).count()
            
            if ready_videos < schedules:
                warnings.append({
                    "type": "low_content",
                    "topic_id": topic.id,
                    "topic_name": topic.name,
                    "ready_videos": ready_videos,
                    "scheduled_posts": schedules,
                    "message": f"Нехватка контента в тематике '{topic.name}': готово {ready_videos}, запланировано {schedules}"
                })
        
        return warnings
    
    def format_report_text(self, report: DailyReport) -> str:
        """Форматировать отчёт в текст для Telegram."""
        text = f"""
📊 Ежедневный отчёт за {report.report_date.strftime('%d.%m.%Y')}

📈 Общая статистика:
   Найдено: {report.total_found}
   Скачано: {report.total_downloaded}
   Обработано: {report.total_processed}
   Опубликовано: {report.total_published}

"""
        
        # Статистика по тематикам
        if report.topics_stats:
            text += "📂 По тематикам:\n"
            topics = self.db.query(Topic).all()
            for topic in topics:
                if topic.id in report.topics_stats:
                    stats = report.topics_stats[topic.id]
                    text += f"   {topic.name}:\n"
                    text += f"      Найдено: {stats['found']}, Обработано: {stats['processed']}, Опубликовано: {stats['published']}\n"
        
        # Ошибки
        if report.errors:
            text += f"\n❌ Ошибки ({len(report.errors)}):\n"
            for error in report.errors[:5]:  # Показываем первые 5
                text += f"   {error['message'][:100]}\n"
        
        # Предупреждения
        if report.warnings:
            text += f"\n⚠️ Предупреждения ({len(report.warnings)}):\n"
            for warning in report.warnings:
                text += f"   {warning['message']}\n"
        
        return text
    
    def update_publication_metrics(self):
        """Обновить метрики всех публикаций."""
        from database.models import PlatformType
        
        publications = self.db.query(Publication).filter(
            Publication.status == "published",
            Publication.platform_post_id.isnot(None)
        ).all()
        
        updated_count = 0
        
        for pub in publications:
            try:
                # Создаем публикатор
                account = self.db.query(Account).filter(Account.id == pub.account_id).first()
                if not account:
                    continue
                
                publisher = None
                if account.platform == PlatformType.PLATFORM_A:
                    publisher = TikTokPublisher(account)
                elif account.platform == PlatformType.PLATFORM_B:
                    publisher = YouTubePublisher(account)
                elif account.platform == PlatformType.PLATFORM_C:
                    publisher = InstagramPublisher(account)
                
                if not publisher:
                    continue
                
                # Получаем метрики
                metrics = publisher.get_metrics(pub.platform_post_id)
                
                if metrics:
                    pub.views = metrics.get("views", 0)
                    pub.likes = metrics.get("likes", 0)
                    pub.comments = metrics.get("comments", 0)
                    pub.shares = metrics.get("shares", 0)
                    pub.last_metrics_update = datetime.utcnow()
                    updated_count += 1
            
            except Exception as e:
                logger.error(f"Ошибка обновления метрик публикации {pub.id}: {e}")
        
        self.db.commit()
        logger.info(f"Обновлено метрик: {updated_count}")
        return updated_count
