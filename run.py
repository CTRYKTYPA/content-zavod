"""Простой скрипт для запуска системы."""
import sys
from pathlib import Path

def main():
    """Простой запуск."""
    print("🚀 Запуск системы управления контентом...")
    
    # Проверяем базовые вещи
    print("\n📋 Проверка...")
    
    # 1. Проверка .env
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  Файл .env не найден!")
        print("   Создайте его на основе .env.example")
        return
    
    # 2. Инициализация БД
    print("📦 Инициализация базы данных...")
    try:
        from database import init_db
        init_db()
        print("✅ База данных готова")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return
    
    # 3. Проверка тематик
    print("📂 Проверка тематик...")
    try:
        from database import get_db
        from modules.content_manager import ContentManager
        
        db = next(get_db())
        manager = ContentManager(db)
        topics = manager.get_all_topics()
        
        if not topics:
            print("⚠️  Тематики не найдены")
            print("   Запустите: python scripts/setup_topics.py")
        else:
            print(f"✅ Найдено тематик: {len(topics)}")
        
        db.close()
    except Exception as e:
        print(f"⚠️  Ошибка проверки: {e}")
    
    # 4. Запуск основного приложения
    print("\n🎬 Запуск Telegram-бота...")
    print("   Для остановки нажмите Ctrl+C\n")
    
    try:
        from main import main as main_app
        main_app()
    except KeyboardInterrupt:
        print("\n\n👋 Остановка системы...")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
