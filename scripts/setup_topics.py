"""Скрипт для создания тематик и начальной настройки."""
import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import get_db
from modules.content_manager import ContentManager
from database.models import PlatformType
from loguru import logger

def setup_topics():
    """Создать тематики и базовую настройку."""
    db = next(get_db())
    manager = ContentManager(db)
    
    try:
        # Список тематик
        topics_data = [
            {
                "name": "Юмор",
                "description": "Юмористический контент",
                "base_tags": ["юмор", "смех", "приколы", "комедия"],
                "tag_pool": ["смешно", "юмор", "прикол", "комедия", "смех", "веселье", "шутка"],
                "description_template": "{emoji} {description}\n\n{cta}"
            },
            {
                "name": "Фильмы",
                "description": "Вырезки из сериалов и фильмов",
                "base_tags": ["фильмы", "сериалы", "кино", "вырезки"],
                "tag_pool": ["фильм", "сериал", "кино", "вырезка", "сцена", "момент", "цитата"],
                "description_template": "{emoji} {description}\n\n{cta}"
            },
            {
                "name": "Познавательный",
                "description": "Познавательный контент и факты",
                "base_tags": ["факты", "познавательно", "интересно", "образование"],
                "tag_pool": ["факт", "познавательно", "интересно", "образование", "знание", "наука"],
                "description_template": "{emoji} {description}\n\n{cta}"
            },
            {
                "name": "Бизнес",
                "description": "Бизнес, деньги, мотивация",
                "base_tags": ["бизнес", "деньги", "мотивация", "успех"],
                "tag_pool": ["бизнес", "деньги", "мотивация", "успех", "богатство", "финансы", "карьера"],
                "description_template": "{emoji} {description}\n\n{cta}"
            },
            {
                "name": "Комедийный контент",
                "description": "Скетчи, короткие сценки, юмористические диалоги, кринж-ситуации",
                "base_tags": ["комедия", "скетч", "сценка", "диалог", "кринж"],
                "tag_pool": ["комедия", "скетч", "сценка", "диалог", "кринж", "юмор", "смешно"],
                "description_template": "{emoji} {description}\n\n{cta}"
            }
        ]
        
        created_topics = []
        
        from database.models import Topic
        
        for topic_data in topics_data:
            # Проверяем, существует ли уже тематика
            existing = db.query(Topic).filter(Topic.name == topic_data["name"]).first()
            if existing:
                logger.info(f"Тематика '{topic_data['name']}' уже существует, пропускаем")
                continue
            
            topic = manager.create_topic(
                name=topic_data["name"],
                description=topic_data["description"],
                base_tags=topic_data["base_tags"],
                tag_pool=topic_data["tag_pool"],
                description_template=topic_data["description_template"]
            )
            created_topics.append(topic)
            logger.info(f"Создана тематика: {topic.name} (ID: {topic.id})")
        
        logger.info(f"Создано тематик: {len(created_topics)}")
        
        # Выводим информацию о созданных тематиках
        print("\n✅ Созданные тематики:")
        for topic in created_topics:
            print(f"  - {topic.id}. {topic.name}")
        
        print("\n💡 Следующие шаги:")
        print("  1. Добавьте источники контента через Telegram-бота или API")
        print("  2. Добавьте аккаунты для публикации")
        print("  3. Настройте расписание публикаций")
    
    finally:
        db.close()

if __name__ == "__main__":
    setup_topics()
