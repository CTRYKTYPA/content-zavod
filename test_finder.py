"""
Тест модуля поиска и сохранения ссылок на видео.
Проверяет что модуль находит видео и сохраняет ссылки.
"""
import sys
from pathlib import Path
from loguru import logger

# Настройка логирования
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>", level="INFO")

from modules.content_collector.instagram_video_finder import InstagramVideoFinder


def test_find_and_save():
    """Тест поиска и сохранения ссылок."""
    print("\n" + "="*80)
    print("ТЕСТ ПОИСКА И СОХРАНЕНИЯ ССЫЛОК НА ВИДЕО")
    print("="*80)
    
    finder = InstagramVideoFinder()
    
    # Тест 1: Поиск в профиле
    print("\n" + "-"*80)
    print("ТЕСТ 1: Поиск видео в профиле")
    print("-"*80)
    
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = input("\nВведите имя профиля для теста (например: instagram): ").strip()
        if not username:
            username = "instagram"  # Дефолтный тестовый профиль
    
    limit = 5  # Берем только 5 для быстрого теста
    
    logger.info(f"Ищу {limit} видео в профиле @{username}...")
    
    try:
        video_urls = finder.find_videos_from_profile(username, limit)
        
        if video_urls:
            logger.info(f"\n[SUCCESS] Найдено {len(video_urls)} видео!")
            print("\nНайденные ссылки:")
            for i, url in enumerate(video_urls, 1):
                print(f"  {i}. {url}")
            
            # Сохраняем ссылки
            print("\n" + "-"*80)
            print("ТЕСТ 2: Сохранение ссылок в файл")
            print("-"*80)
            
            links_file = finder.save_links(video_urls)
            logger.info(f"[SUCCESS] Ссылки сохранены в: {links_file}")
            
            # Проверяем что файл создан и читаем его
            print("\n" + "-"*80)
            print("ТЕСТ 3: Проверка сохраненного файла")
            print("-"*80)
            
            if links_file.exists():
                logger.info(f"[SUCCESS] Файл существует: {links_file}")
                
                # Читаем файл
                loaded_urls = finder.load_links(links_file.name)
                
                if loaded_urls:
                    logger.info(f"[SUCCESS] Загружено {len(loaded_urls)} ссылок из файла")
                    
                    # Сравниваем
                    if len(loaded_urls) == len(video_urls):
                        logger.info("[SUCCESS] Количество ссылок совпадает!")
                    else:
                        logger.warning(f"Несоответствие: сохранено {len(video_urls)}, загружено {len(loaded_urls)}")
                    
                    # Показываем первые несколько
                    print("\nПервые 3 ссылки из файла:")
                    for i, url in enumerate(loaded_urls[:3], 1):
                        print(f"  {i}. {url}")
                else:
                    logger.error("[FAIL] Не удалось загрузить ссылки из файла")
            else:
                logger.error(f"[FAIL] Файл не создан: {links_file}")
            
        else:
            logger.warning(f"[FAIL] Видео не найдены в профиле @{username}")
            logger.info("Возможные причины:")
            logger.info("  1. Профиль приватный")
            logger.info("  2. В профиле нет видео")
            logger.info("  3. Проблемы с доступом (нужен VPN)")
    
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при поиске: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    # Итоги
    print("\n" + "="*80)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*80)
    
    # Проверяем папку со ссылками
    links_dir = Path("instagram_links")
    if links_dir.exists():
        links_files = list(links_dir.glob("*.txt"))
        logger.info(f"\nВсего файлов со ссылками: {len(links_files)}")
        if links_files:
            print("\nПоследние 3 файла:")
            for f in sorted(links_files, key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                size = f.stat().st_size
                print(f"  - {f.name} ({size} байт)")
    
    print("\n" + "="*80)


if __name__ == '__main__':
    test_find_and_save()
