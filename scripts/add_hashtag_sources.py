"""Скрипт для добавления источников по хэштегам для тестирования."""
from database import get_db
from modules.content_manager import ContentManager
from loguru import logger

def add_hashtag_sources():
    """Добавить источники по хэштегам для каждой тематики."""
    db = next(get_db())
    manager = ContentManager(db)
    
    try:
        # Получаем все тематики
        topics = manager.get_all_topics()
        
        # Хэштеги для каждой тематики
        hashtags_by_topic = {
            "Юмор": ["юмор", "приколы", "смех", "комедия", "смешно"],
            "Фильмы": ["фильмы", "сериалы", "кино", "вырезки", "сцены"],
            "Познавательный": ["факты", "познавательно", "интересно", "образование", "наука"],
            "Бизнес": ["бизнес", "деньги", "мотивация", "успех", "финансы"],
            "Комедийный контент": ["комедия", "скетч", "сценка", "диалог", "кринж"]
        }
        
        added_count = 0
        
        for topic in topics:
            hashtags = hashtags_by_topic.get(topic.name, [])
            
            for hashtag in hashtags:
                # Проверяем, не существует ли уже такой источник
                existing = db.query(ContentSource).filter(
                    ContentSource.topic_id == topic.id,
                    ContentSource.source_type == "hashtag",
                    ContentSource.source_value == hashtag
                ).first()
                
                if existing:
                    logger.info(f"Источник #{hashtag} уже существует для тематики {topic.name}")
                    continue
                
                # Добавляем источник с фильтрами: 1 млн просмотров ИЛИ 10к лайков
                source = manager.add_source(
                    topic_id=topic.id,
                    source_type="hashtag",
                    source_value=hashtag,
                    min_views=1000000,  # 1 млн просмотров
                    min_likes=10000     # 10к лайков
                )
                added_count += 1
                logger.info(f"Добавлен источник #{hashtag} для тематики {topic.name}")
        
        print(f"\n✅ Добавлено источников: {added_count}")
        print("\n💡 Теперь можно запустить сбор контента!")
    
    finally:
        db.close()

if __name__ == "__main__":
    add_hashtag_sources()
