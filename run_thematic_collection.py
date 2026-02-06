"""
Запуск тематического сбора видео для всех 5 тем.
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger

# Настройка логирования (без эмодзи для Windows)
logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level: <8} | {message}", level="INFO")

from database.models import Base, Topic
from config import settings

# Импортируем сборщики
from modules.thematic_collectors.humor_collector import HumorCollector
from modules.thematic_collectors.business_collector import BusinessCollector
from modules.thematic_collectors.lifestyle_collector import LifestyleCollector
from modules.thematic_collectors.tech_collector import TechCollector
from modules.thematic_collectors.motivation_collector import MotivationCollector


def main():
    print("\n" + "="*80)
    print("ТЕМАТИЧЕСКИЙ СБОР ВИДЕО С INSTAGRAM")
    print("="*80)
    
    # Подключаемся к БД
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Получаем параметры из аргументов
    if len(sys.argv) > 1:
        theme_name = sys.argv[1].lower()
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    else:
        print("\nДоступные темы:")
        print("1. Юмор (humor)")
        print("2. Бизнес (business)")
        print("3. Лайфстайл (lifestyle)")
        print("4. Технологии (tech)")
        print("5. Мотивация (motivation)")
        print("6. Все темы (all)")
        
        choice = input("\nВыберите тему (1-6) или название: ").strip().lower()
        
        if choice in ["1", "humor", "юмор"]:
            theme_name = "humor"
        elif choice in ["2", "business", "бизнес"]:
            theme_name = "business"
        elif choice in ["3", "lifestyle", "лайфстайл"]:
            theme_name = "lifestyle"
        elif choice in ["4", "tech", "технологии"]:
            theme_name = "tech"
        elif choice in ["5", "motivation", "мотивация"]:
            theme_name = "motivation"
        elif choice in ["6", "all", "все"]:
            theme_name = "all"
        else:
            theme_name = choice
        
        limit_input = input("Сколько видео найти по каждой теме (по умолчанию 5): ").strip()
        limit = int(limit_input) if limit_input else 5
    
    # Маппинг тем
    theme_mapping = {
        "humor": ("Юмор", HumorCollector),
        "business": ("Бизнес", BusinessCollector),
        "lifestyle": ("Лайфстайл", LifestyleCollector),
        "tech": ("Технологии", TechCollector),
        "motivation": ("Мотивация", MotivationCollector),
    }
    
    results = []
    
    if theme_name == "all":
        # Запускаем для всех тем
        for theme_key, (theme_display_name, CollectorClass) in theme_mapping.items():
            logger.info(f"\n{'='*80}")
            logger.info(f"ОБРАБОТКА ТЕМЫ: {theme_display_name}")
            logger.info(f"{'='*80}")
            
            topic = db.query(Topic).filter(Topic.name == theme_display_name).first()
            if not topic:
                logger.error(f"Тематика '{theme_display_name}' не найдена в БД!")
                logger.info("Запустите сначала: python scripts/setup_thematic_topics.py")
                continue
            
            collector = CollectorClass(db, topic)
            result = collector.collect_and_download(limit=limit, download=True)
            results.append(result)
    else:
        # Запускаем для одной темы
        if theme_name not in theme_mapping:
            logger.error(f"Неизвестная тема: {theme_name}")
            logger.info(f"Доступные темы: {', '.join(theme_mapping.keys())}")
            db.close()
            return
        
        theme_display_name, CollectorClass = theme_mapping[theme_name]
        
        logger.info(f"Обработка темы: {theme_display_name}")
        
        topic = db.query(Topic).filter(Topic.name == theme_display_name).first()
        if not topic:
            logger.error(f"Тематика '{theme_display_name}' не найдена в БД!")
            logger.info("Запустите сначала: python scripts/setup_thematic_topics.py")
            db.close()
            return
        
        collector = CollectorClass(db, topic)
        result = collector.collect_and_download(limit=limit, download=True)
        results.append(result)
    
    db.close()
    
    # Итоговый отчет
    logger.info(f"\n{'='*80}")
    logger.info("ИТОГОВЫЙ ОТЧЕТ")
    logger.info(f"{'='*80}")
    
    total_found = sum(r['found'] for r in results)
    total_saved = sum(r['saved_to_db'] for r in results)
    total_downloaded = sum(r['downloaded'] for r in results)
    total_failed = sum(r['failed'] for r in results)
    
    logger.info(f"\nВсего найдено: {total_found}")
    logger.info(f"Сохранено в БД: {total_saved}")
    logger.info(f"Скачано: {total_downloaded}")
    logger.info(f"Ошибок: {total_failed}")
    
    for result in results:
        logger.info(f"\n{result['theme']}: найдено {result['found']}, сохранено {result['saved_to_db']}, скачано {result['downloaded']}")
    
    logger.info(f"\n{'='*80}")


if __name__ == '__main__':
    main()
