"""Тест загрузки видео из Instagram."""
import sys
import codecs
from pathlib import Path

# Настройка UTF-8 для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Добавляем корень проекта в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import get_db, init_db
from modules.content_manager import ContentManager
from database.models import ContentSource, Video, VideoStatus

print("=" * 60)
print("ТЕСТ ЗАГРУЗКИ ВИДЕО ИЗ INSTAGRAM")
print("=" * 60)

# Инициализация
init_db()
db = next(get_db())
manager = ContentManager(db)

# Получаем первую тематику
from database.models import Topic
topics = db.query(Topic).all()
if not topics:
    print("❌ Тематики не найдены! Сначала запустите: python create_topics.py")
    db.close()
    exit(1)

topic = topics[0]
print(f"\n📂 Используем тематику: {topic.name} (ID: {topic.id})")

# Проверяем источники
sources = manager.get_sources_by_topic(topic.id)
if not sources:
    print("\n📝 Создаю тестовый источник...")
    # Пробуем использовать профиль вместо хэштега (работает лучше)
    # Используем популярный профиль с видео
    test_profiles = ["natgeo", "bbcearth", "nasa", "natgeotravel"]
    profile_used = None
    
    for test_profile in test_profiles:
        try:
            source = manager.add_source(
                topic_id=topic.id,
                source_type="profile",
                source_value=test_profile,  # Популярный профиль для теста
                min_views=50000,  # Снижаем порог для теста (50к вместо 1млн)
                min_likes=500    # Снижаем порог для теста (500 вместо 10к)
            )
            profile_used = test_profile
            print(f"✅ Создан источник: @{source.source_value}")
            sources = [source]
            break
        except Exception as e:
            print(f"⚠️  Не удалось создать источник для @{test_profile}: {e}")
            continue
    
    # Если профили не сработали, пробуем хэштег
    if not sources:
        print("Пробую создать источник по хэштегу...")
        source = manager.add_source(
            topic_id=topic.id,
            source_type="hashtag",
            source_value="funny",  # Популярный хэштег для теста
            min_views=100000,  # Снижаем порог для теста (100к вместо 1млн)
            min_likes=1000    # Снижаем порог для теста (1к вместо 10к)
        )
        print(f"✅ Создан источник: #{source.source_value}")
        sources = [source]
else:
    print(f"\n📋 Найдено источников: {len(sources)}")
    source = sources[0]
    print(f"   Используем: {source.source_type} - {source.source_value}")

# Сбор видео
print("\n🔍 Собираю видео из Instagram...")
print("   Это может занять 1-2 минуты...")
print("   (Если Instagram заблокирован, включите VPN)")
print("   (Используется HTML парсинг через yt-dlp - обходит GraphQL API)")
print("   (Для хэштегов требуется авторизация)")

try:
    import signal
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Превышен таймаут сбора видео")
    
    # Устанавливаем таймаут 3 минуты
    if hasattr(signal, 'SIGALRM'):  # Unix
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(180)
    
    videos = manager.collect_content_from_source(source.id, limit=3)
    
    if hasattr(signal, 'SIGALRM'):
        signal.alarm(0)  # Отключаем таймаут
    
    if videos:
        print(f"\n✅ Собрано видео: {len(videos)}")
        print("\n" + "-" * 60)
        
        for i, video in enumerate(videos, 1):
            print(f"\n{i}. Видео ID: {video.id}")
            print(f"   Автор: @{video.source_author}")
            print(f"   Описание: {(video.description or 'Нет описания')[:60]}...")
            print(f"   Статус: {video.status.value}")
            
            if video.metadata_json:
                metadata = video.metadata_json
                views = metadata.get("view_count") or metadata.get("views") or 0
                likes = metadata.get("likes") or 0
                print(f"   Просмотры: {views:,}")
                print(f"   Лайки: {likes:,}")
            
            print(f"   URL: {video.source_url}")
        
        print("\n" + "-" * 60)
        
        # Пробуем скачать первое видео
        print(f"\n⬇️  Скачиваю первое видео (ID: {videos[0].id})...")
        print("   Это может занять некоторое время...")
        
        success = manager.download_video(videos[0].id)
        
        if success:
            video = db.query(Video).filter(Video.id == videos[0].id).first()
            print(f"\n✅ Видео успешно скачано!")
            print(f"   Путь: {video.original_file_path}")
            
            # Проверяем размер файла
            if video.original_file_path:
                file_path = Path(video.original_file_path)
                if file_path.exists():
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    print(f"   Размер: {size_mb:.2f} MB")
                    print(f"   ✅ Файл существует на диске!")
                else:
                    print(f"   ⚠️  Файл не найден по пути")
        else:
            video = db.query(Video).filter(Video.id == videos[0].id).first()
            if video and video.error_message:
                print(f"\n❌ Ошибка скачивания: {video.error_message}")
            else:
                print(f"\n❌ Ошибка скачивания")
    else:
        print("\n⚠️  Видео не найдено")
        print("\nВозможные причины:")
        print("  1. Нет видео с такими метриками (100к просмотров или 1к лайков)")
        print("  2. Требуется авторизация в Instagram")
        print("  3. Instagram заблокирован (нужен VPN)")
        print("  4. Проблемы с доступом к Instagram")
        print("\nПопробуйте:")
        print("  - Добавить авторизацию в .env (INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)")
        print("  - Включить VPN")
        print("  - Снизить пороги фильтров")

except Exception as e:
    print(f"\n❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
    print("\nВозможные решения:")
    print("  1. Проверьте подключение к интернету")
    print("  2. Включите VPN если Instagram заблокирован")
    print("  3. Добавьте авторизацию в .env")
    print("  4. Проверьте логи в папке logs/")

finally:
    db.close()

print("\n" + "=" * 60)
print("Тест завершён!")
print("=" * 60)
