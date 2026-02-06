"""Скрипт для проверки готовности системы к запуску."""
import sys
from pathlib import Path
from loguru import logger

def check_setup():
    """Проверить готовность системы."""
    print("=" * 60)
    print("ПРОВЕРКА ГОТОВНОСТИ СИСТЕМЫ")
    print("=" * 60)
    
    errors = []
    warnings = []
    
    # 1. Проверка Python версии
    print("\n1. Проверка версии Python...")
    if sys.version_info < (3, 9):
        errors.append(f"Требуется Python 3.9+, установлена {sys.version}")
        print(f"❌ Python {sys.version}")
    else:
        print(f"✅ Python {sys.version.split()[0]}")
    
    # 2. Проверка зависимостей
    print("\n2. Проверка зависимостей...")
    required_packages = [
        "instaloader",
        "sqlalchemy",
        "telegram",
        "celery",
        "redis",
        "loguru",
        "moviepy",
        "Pillow",
        "opencv-python",
        "requests"
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"   ✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"   ❌ {package} - не установлен")
    
    if missing_packages:
        errors.append(f"Отсутствуют пакеты: {', '.join(missing_packages)}")
        print(f"\n   Установите: pip install {' '.join(missing_packages)}")
    
    # 3. Проверка файлов конфигурации
    print("\n3. Проверка конфигурации...")
    env_file = Path(".env")
    if not env_file.exists():
        warnings.append("Файл .env не найден. Создайте его на основе .env.example")
        print("   ⚠️  Файл .env не найден")
    else:
        print("   ✅ Файл .env найден")
        
        # Проверяем важные настройки
        from config import settings
        
        if not settings.TELEGRAM_BOT_TOKEN:
            warnings.append("TELEGRAM_BOT_TOKEN не установлен")
            print("   ⚠️  TELEGRAM_BOT_TOKEN не установлен")
        else:
            print("   ✅ TELEGRAM_BOT_TOKEN установлен")
        
        if not settings.TELEGRAM_ADMIN_IDS:
            warnings.append("TELEGRAM_ADMIN_IDS не установлен")
            print("   ⚠️  TELEGRAM_ADMIN_IDS не установлен")
        else:
            print(f"   ✅ TELEGRAM_ADMIN_IDS установлен ({len(settings.TELEGRAM_ADMIN_IDS)} админов)")
    
    # 4. Проверка директорий
    print("\n4. Проверка директорий...")
    from config import settings
    
    dirs_to_check = [
        ("downloads", settings.DOWNLOADS_DIR),
        ("processed", settings.PROCESSED_DIR),
        ("logs", settings.LOGS_DIR),
    ]
    
    for name, path in dirs_to_check:
        if path.exists():
            print(f"   ✅ {name}/")
        else:
            print(f"   ⚠️  {name}/ - будет создана автоматически")
    
    # 5. Проверка базы данных
    print("\n5. Проверка подключения к базе данных...")
    try:
        from database import engine
        with engine.connect() as conn:
            print("   ✅ Подключение к БД успешно")
    except Exception as e:
        errors.append(f"Не удалось подключиться к БД: {e}")
        print(f"   ❌ Ошибка подключения: {e}")
        print("   Проверьте DATABASE_URL в .env")
    
    # 6. Проверка Redis
    print("\n6. Проверка подключения к Redis...")
    try:
        import redis
        from config import settings
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        print("   ✅ Подключение к Redis успешно")
    except Exception as e:
        warnings.append(f"Не удалось подключиться к Redis: {e}")
        print(f"   ⚠️  Redis недоступен: {e}")
        print("   Celery будет работать без Redis (не рекомендуется)")
    
    # 7. Проверка instaloader
    print("\n7. Проверка instaloader...")
    try:
        import instaloader
        L = instaloader.Instaloader(quiet=True)
        print("   ✅ Instaloader работает")
    except Exception as e:
        errors.append(f"Ошибка instaloader: {e}")
        print(f"   ❌ Ошибка: {e}")
    
    # Итоги
    print("\n" + "=" * 60)
    if errors:
        print("❌ ОБНАРУЖЕНЫ КРИТИЧЕСКИЕ ОШИБКИ:")
        for error in errors:
            print(f"   - {error}")
        print("\nИсправьте ошибки перед запуском системы!")
    else:
        print("✅ КРИТИЧЕСКИХ ОШИБОК НЕ ОБНАРУЖЕНО")
    
    if warnings:
        print("\n⚠️  ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings:
            print(f"   - {warning}")
        print("\nСистема может работать, но рекомендуется исправить предупреждения.")
    
    if not errors and not warnings:
        print("\n🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
        print("Система готова к запуску!")
    
    print("=" * 60)
    
    return len(errors) == 0

if __name__ == "__main__":
    try:
        success = check_setup()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        logger.exception("Детали:")
        sys.exit(1)
