"""Telegram-бот для управления системой."""
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from loguru import logger

from config import settings
from database.models import Topic, Account, Video, VideoStatus, PlatformType, ContentSource
from modules.content_manager import ContentManager
from modules.scheduler import PublicationScheduler


class TelegramBot:
    """Telegram-бот для управления системой."""
    
    def __init__(self, db: Session):
        """
        Инициализация бота.
        
        Args:
            db: Сессия базы данных
        """
        if not settings.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN не установлен в конфигурации")
        
        self.db = db
        self.content_manager = ContentManager(db)
        self.scheduler = PublicationScheduler(db)
        
        # Создаем приложение
        self.application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
        
        # Регистрируем handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Зарегистрировать обработчики команд."""
        # Команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("topics", self.topics_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("alerts", self.alerts_command))
        self.application.add_handler(CommandHandler("videos", self.videos_command))
        self.application.add_handler(CommandHandler("accounts", self.accounts_command))
        self.application.add_handler(CommandHandler("myid", self.myid_command))
        
        # Callback handlers
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))
    
    def _is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором."""
        return user_id in settings.TELEGRAM_ADMIN_IDS

    async def myid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ваш Telegram ID (для настройки TELEGRAM_ADMIN_IDS в .env). Доступно всем."""
        uid = update.effective_user.id
        await update.message.reply_text(
            f"🆔 Ваш Telegram ID: `{uid}`\n\n"
            f"Добавьте в .env:\n`TELEGRAM_ADMIN_IDS=[{uid}]`",
            parse_mode="Markdown",
        )
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start."""
        user_id = update.effective_user.id
        
        if not self._is_admin(user_id):
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return
        
        welcome_text = """
👋 Добро пожаловать в систему управления контентом!

Доступные команды:
/topics - Тематики
/accounts - Аккаунты
/videos - Видео (статусы по роликам)
/status - Статус системы
/stats - Статистика по темам
/alerts - Мало контента? Ошибки?
/help - Справка
/myid - Ваш Telegram ID
        """
        
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help."""
        help_text = """
📖 Справка по командам:

/topics - Тематики
/accounts - Аккаунты
/videos [topic_id] - Видео и статусы по роликам
/status - Статус системы
/stats - Статистика по темам (очередь, ошибки)
/alerts - Мало контента? Есть ошибки?
/myid - Ваш Telegram ID (для настройки админов)
        """
        await update.message.reply_text(help_text)
    
    async def topics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /topics."""
        if not self._is_admin(update.effective_user.id):
            return
        
        topics = self.content_manager.get_all_topics(active_only=False)
        
        if not topics:
            await update.message.reply_text("📂 Тематики не найдены.")
            return
        
        text = "📂 Тематики:\n\n"
        keyboard = []
        
        for topic in topics:
            status = "✅" if topic.is_active else "❌"
            text += f"{status} {topic.id}. {topic.name}\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{topic.name} ({'активна' if topic.is_active else 'неактивна'})",
                    callback_data=f"topic_{topic.id}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def accounts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /accounts."""
        if not self._is_admin(update.effective_user.id):
            return
        
        accounts = self.db.query(Account).all()
        
        if not accounts:
            await update.message.reply_text("👤 Аккаунты не найдены.")
            return
        
        text = "👤 Аккаунты:\n\n"
        
        for account in accounts:
            status = "✅" if account.is_active else "❌"
            topic = self.content_manager.get_topic(account.topic_id)
            text += f"{status} {account.platform.value} - @{account.username}\n"
            text += f"   Тематика: {topic.name if topic else 'N/A'}\n\n"
        
        await update.message.reply_text(text)
    
    async def videos_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /videos."""
        if not self._is_admin(update.effective_user.id):
            return
        
        args = context.args
        topic_id = int(args[0]) if args else None
        
        query = self.db.query(Video)
        if topic_id:
            query = query.filter(Video.topic_id == topic_id)
        
        videos = query.order_by(Video.created_at.desc()).limit(20).all()
        
        if not videos:
            await update.message.reply_text("🎬 Видео не найдены.")
            return
        
        text = f"🎬 Видео ({len(videos)} последних):\n\n"
        
        for video in videos[:10]:  # Показываем первые 10
            status_emoji = {
                VideoStatus.FOUND: "🔍",
                VideoStatus.DOWNLOADED: "⬇️",
                VideoStatus.PROCESSING: "⚙️",
                VideoStatus.PROCESSED: "✅",
                VideoStatus.IN_QUEUE: "⏳",
                VideoStatus.PUBLISHED: "📤",
                VideoStatus.ERROR: "❌",
            }.get(video.status, "❓")
            
            text += f"{status_emoji} {video.id}. {video.source_author or 'N/A'}\n"
            text += f"   Статус: {video.status.value}\n"
            if video.error_message:
                text += f"   Ошибка: {video.error_message[:50]}\n"
            text += "\n"
        
        await update.message.reply_text(text)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status."""
        if not self._is_admin(update.effective_user.id):
            return
        
        # Статистика по тематикам
        topics = self.content_manager.get_all_topics(active_only=True)
        
        total_videos = self.db.query(Video).count()
        found = self.db.query(Video).filter(Video.status == VideoStatus.FOUND).count()
        downloaded = self.db.query(Video).filter(Video.status == VideoStatus.DOWNLOADED).count()
        processed = self.db.query(Video).filter(Video.status == VideoStatus.PROCESSED).count()
        published = self.db.query(Video).filter(Video.status == VideoStatus.PUBLISHED).count()
        errors = self.db.query(Video).filter(Video.status == VideoStatus.ERROR).count()

        total_accounts = self.db.query(Account).count()
        active_accounts = self.db.query(Account).filter(Account.is_active == True).count()

        text = f"""
📊 Статус системы (Этап 1):

📂 Тематики: {len(topics)} активных
👤 Аккаунты: {active_accounts}/{total_accounts} активных

🎬 Видео:
   Всего: {total_videos}
   🔍 Найдено: {found}
   ⬇️ Скачано: {downloaded}
   ⚙️ Обработано (готовы к публикации): {processed}
   📤 Опубликовано: {published}
   ❌ Ошибок: {errors}
"""
        await update.message.reply_text(text)

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика по темам: найденные, в очереди, ошибки."""
        if not self._is_admin(update.effective_user.id):
            return
        topics = self.content_manager.get_all_topics(active_only=False)
        since = datetime.utcnow() - timedelta(hours=24)
        lines = ["📊 Статистика по темам\n"]
        total_queue = 0
        total_errors = 0
        for t in topics:
            vq = self.db.query(Video).filter(Video.topic_id == t.id, Video.status == VideoStatus.PROCESSED).count()
            err = self.db.query(Video).filter(Video.topic_id == t.id, Video.status == VideoStatus.ERROR).count()
            err_24 = self.db.query(Video).filter(
                Video.topic_id == t.id,
                Video.status == VideoStatus.ERROR,
                Video.updated_at >= since,
            ).count()
            total_queue += vq
            total_errors += err
            lines.append(f"📂 {t.name}: в очереди {vq}, ошибок {err} (за 24ч: {err_24})")
        lines.append(f"\n⏳ Всего в очереди: {total_queue}")
        lines.append(f"❌ Всего ошибок: {total_errors}")
        await update.message.reply_text("\n".join(lines))

    async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка: мало контента в очереди или есть свежие ошибки."""
        if not self._is_admin(update.effective_user.id):
            return
        ALERT_QUEUE_MIN = 5
        since = datetime.utcnow() - timedelta(hours=24)
        ready = self.db.query(Video).filter(Video.status == VideoStatus.PROCESSED).count()
        errors_24 = self.db.query(Video).filter(
            Video.status == VideoStatus.ERROR,
            Video.updated_at >= since,
        ).count()
        alerts = []
        if ready < ALERT_QUEUE_MIN:
            alerts.append(f"⚠️ Мало контента (готовых к публикации): {ready} (рекомендуется ≥ {ALERT_QUEUE_MIN})")
        if errors_24 > 0:
            alerts.append(f"⚠️ За последние 24 ч ошибок: {errors_24}")
        if not alerts:
            await update.message.reply_text("✅ Всё в порядке: очередь в норме, свежих ошибок нет.")
            return
        await update.message.reply_text("\n".join(alerts))
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов."""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("topic_"):
            topic_id = int(data.split("_")[1])
            await self._show_topic_details(query, topic_id)
    
    async def _show_topic_details(self, query, topic_id: int):
        """Показать детали тематики."""
        topic = self.content_manager.get_topic(topic_id)
        if not topic:
            await query.edit_message_text("Тематика не найдена.")
            return
        
        videos_count = self.db.query(Video).filter(Video.topic_id == topic_id).count()
        accounts_count = self.db.query(Account).filter(Account.topic_id == topic_id).count()
        sources_count = self.db.query(ContentSource).filter(ContentSource.topic_id == topic_id).count()
        found = self.db.query(Video).filter(Video.topic_id == topic_id, Video.status == VideoStatus.FOUND).count()
        downloaded = self.db.query(Video).filter(Video.topic_id == topic_id, Video.status == VideoStatus.DOWNLOADED).count()
        processed = self.db.query(Video).filter(Video.topic_id == topic_id, Video.status == VideoStatus.PROCESSED).count()
        published = self.db.query(Video).filter(Video.topic_id == topic_id, Video.status == VideoStatus.PUBLISHED).count()
        errors = self.db.query(Video).filter(Video.topic_id == topic_id, Video.status == VideoStatus.ERROR).count()

        text = f"""
📂 {topic.name}

{topic.description or 'Без описания'}

Статистика:
   Видео всего: {videos_count}
   🔍 Найдено: {found}  ⬇️ Скачано: {downloaded}  ⚙️ Обработано: {processed}
   ⏳ Готовы к публикации: {processed}  📤 Опубликовано: {published}  ❌ Ошибок: {errors}
   Аккаунты: {accounts_count}  Источники: {sources_count}

{'✅ Активна' if topic.is_active else '❌ Неактивна'}
"""
        await query.edit_message_text(text)
    
    def run(self):
        """Запустить бота."""
        logger.info("Запуск Telegram-бота...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
