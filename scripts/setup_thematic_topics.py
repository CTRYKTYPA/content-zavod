"""
Скрипт для создания 5 тематик в БД и соответствующих папок.
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.models import Base, Topic
from database import get_db
from config import settings
from loguru import logger


def setup_thematic_topics():
    """Создать 5 тематик в БД и папки для них."""
    
    # Создаем таблицы если их нет
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Определяем тематики
    themes = [
        {
            "name": "Юмор",
            "description": "Смешные видео, комедия, шутки",
            "folder": "humor"
        },
        {
            "name": "Бизнес",
            "description": "Бизнес, предпринимательство, успех",
            "folder": "business"
        },
        {
            "name": "Лайфстайл",
            "description": "Образ жизни, повседневность, влоги",
            "folder": "lifestyle"
        },
        {
            "name": "Технологии",
            "description": "Технологии, гаджеты, инновации",
            "folder": "tech"
        },
        {
            "name": "Мотивация",
            "description": "Мотивация, вдохновение, достижения",
            "folder": "motivation"
        }
    ]
    
    created_topics = []
    
    for theme_data in themes:
        # Проверяем, существует ли уже тематика
        existing = db.query(Topic).filter(Topic.name == theme_data["name"]).first()
        
        if existing:
            logger.info(f"Тематика '{theme_data['name']}' уже существует (ID: {existing.id})")
            created_topics.append(existing)
        else:
            # Создаем тематику в БД
            topic = Topic(
                name=theme_data["name"],
                description=theme_data["description"],
                is_active=True
            )
            db.add(topic)
            db.commit()
            db.refresh(topic)
            logger.info(f"Создана тематика: {theme_data['name']} (ID: {topic.id})")
            created_topics.append(topic)
        
        # Создаем папку для тематики
        theme_folder = Path("downloads") / theme_data["folder"]
        theme_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Создана папка: {theme_folder.absolute()}")
    
    db.close()
    
    logger.info(f"\n{'='*70}")
    logger.info("НАСТРОЙКА ЗАВЕРШЕНА")
    logger.info(f"Создано/найдено тематик: {len(created_topics)}")
    logger.info(f"{'='*70}")
    
    return created_topics


if __name__ == '__main__':
    setup_thematic_topics()
