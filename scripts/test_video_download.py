"""Скрипт для тестирования загрузки видео из Instagram."""
from database import get_db, init_db
from modules.content_manager import ContentManager
from database.models import Topic, ContentSource
from loguru import logger
import sys

def test_video_download():
    """Тест загрузки видео."""
    print("=" * 60)
    print("ТЕСТ ЗАГРУЗКИ ВИДЕО ИЗ INSTAGRAM")
    print("=" * 60)
    
    # Инициализация БД
    print("\n1. Проверка базы данных...")
    try:
        init_db()
        print("✅ База данных инициализирована")
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        return False
    
    db = next(get_db())
    manager = ContentManager(db)
    
    # Проверка тематик
    print("\n2. Проверка тематик...")
    topics = manager.get_all_topics()
    if not topics:
        print("⚠️  Тематики не найдены. Создайте их через: python scripts/setup_topics.py")
        print("   Создаю тестовую тематику...")
        topic = manager.create_topic(
            name="Тест",
            description="Тестовая тематика для проверки",
            base_tags=["тест"],
            tag_pool=["тест"]
        )
        print(f"✅ Создана тестовая тематика: {topic.name} (ID: {topic.id})")
        topics = [topic]
    else:
        print(f"✅ Найдено тематик: {len(topics)}")
        for topic in topics[:3]:
            print(f"   - {topic.id}. {topic.name}")
    
    # Проверка источников
    print("\n3. Проверка источников контента...")
    test_topic = topics[0]
    sources = manager.get_sources_by_topic(test_topic.id)
    
    if not sources:
        print("⚠️  Источники не найдены. Создаю тестовый источник...")
        # Создаем тестовый источник по популярному хэштегу
        source = manager.add_source(
            topic_id=test_topic.id,
            source_type="hashtag",
            source_value="funny",  # Популярный хэштег для теста
            min_views=100000,  # Снижаем порог для теста
            min_likes=1000
        )
        print(f"✅ Создан тестовый источник: #{source.source_value}")
        sources = [source]
    else:
        print(f"✅ Найдено источников: {len(sources)}")
        for source in sources[:3]:
            print(f"   - {source.id}. {source.source_type}: {source.source_value}")
    
    # Тест сбора контента
    print("\n4. Тест сбора видео из Instagram...")
    print("   Это может занять некоторое время...")
    
    test_source = sources[0]
    try:
        videos = manager.collect_content_from_source(test_source.id, limit=3)
        
        if videos:
            print(f"✅ Успешно собрано видео: {len(videos)}")
            print("\n   Собранные видео:")
            for i, video in enumerate(videos, 1):
                print(f"\n   {i}. Видео ID: {video.id}")
                print(f"      Автор: {video.source_author}")
                print(f"      Описание: {(video.description or 'Нет описания')[:50]}...")
                print(f"      Статус: {video.status.value}")
                if video.metadata_json:
                    metadata = video.metadata_json
                    views = metadata.get("view_count") or metadata.get("views") or 0
                    likes = metadata.get("likes") or 0
                    print(f"      Просмотры: {views:,}")
                    print(f"      Лайки: {likes:,}")
        else:
            print("⚠️  Видео не найдено. Возможные причины:")
            print("   - Нет видео, соответствующих фильтрам (1 млн просмотров или 10к лайков)")
            print("   - Проблемы с доступом к Instagram")
            print("   - Требуется авторизация в Instagram")
            print("\n   Попробуйте:")
            print("   1. Добавить авторизацию в .env (INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)")
            print("   2. Снизить пороги фильтров (min_views, min_likes)")
            print("   3. Проверить доступ к Instagram (возможно нужен VPN)")
            return False
    
    except Exception as e:
        print(f"❌ Ошибка при сборе видео: {e}")
        logger.exception("Детали ошибки:")
        print("\n   Возможные решения:")
        print("   1. Проверьте подключение к интернету")
        print("   2. Проверьте доступ к Instagram (возможно нужен VPN)")
        print("   3. Добавьте авторизацию в .env")
        print("   4. Проверьте логи в папке logs/")
        return False
    
    # Тест скачивания видео
    print("\n5. Тест скачивания видео...")
    if videos:
        test_video = videos[0]
        print(f"   Скачиваю видео {test_video.id}...")
        
        try:
            success = manager.download_video(test_video.id)
            if success:
                print(f"✅ Видео успешно скачано!")
                print(f"   Путь: {test_video.original_file_path}")
                
                # Проверяем размер файла
                from pathlib import Path
                if test_video.original_file_path:
                    file_path = Path(test_video.original_file_path)
                    if file_path.exists():
                        size_mb = file_path.stat().st_size / (1024 * 1024)
                        print(f"   Размер файла: {size_mb:.2f} MB")
                    else:
                        print("⚠️  Файл не найден по указанному пути")
            else:
                print("❌ Ошибка скачивания видео")
                if test_video.error_message:
                    print(f"   Причина: {test_video.error_message}")
                return False
        except Exception as e:
            print(f"❌ Ошибка при скачивании: {e}")
            logger.exception("Детали ошибки:")
            return False
    else:
        print("⚠️  Нет видео для скачивания")
        return False
    
    print("\n" + "=" * 60)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    print("=" * 60)
    print("\nСистема готова к работе!")
    print("\nСледующие шаги:")
    print("1. Запустите основное приложение: python main.py")
    print("2. В других терминалах запустите Celery:")
    print("   - celery -A modules.scheduler.scheduler.celery_app worker --loglevel=info")
    print("   - celery -A modules.scheduler.scheduler.celery_app beat --loglevel=info")
    print("3. Используйте Telegram-бота для управления")
    
    db.close()
    return True

if __name__ == "__main__":
    try:
        success = test_video_download()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Тест прерван пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
        logger.exception("Детали:")
        sys.exit(1)
