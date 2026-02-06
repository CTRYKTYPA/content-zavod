"""
Автоматический скрипт для поиска и скачивания видео с Instagram.
Использует новый модуль instagram_video_finder.
"""
import sys
from pathlib import Path
from loguru import logger

# Настройка логирования
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>", level="INFO")

from modules.content_collector.instagram_video_finder import InstagramVideoFinder


def main():
    print("\n" + "="*80)
    print("АВТОМАТИЧЕСКИЙ ПОИСК И СКАЧИВАНИЕ ВИДЕО С INSTAGRAM")
    print("="*80)
    
    finder = InstagramVideoFinder()
    
    # Примеры использования
    
    if len(sys.argv) > 1:
        # Режим из командной строки
        if len(sys.argv) < 3:
            print("\nИспользование:")
            print("  python auto_download_videos.py profile <username> [limit]")
            print("  python auto_download_videos.py hashtag <hashtag> [limit]")
            print("  python auto_download_videos.py links <filename>")
            print("\nПримеры:")
            print("  python auto_download_videos.py profile instagram 10")
            print("  python auto_download_videos.py hashtag travel 5")
            print("  python auto_download_videos.py links video_links_20240122.txt")
            sys.exit(1)
        
        mode = sys.argv[1].lower()
        
        if mode == "profile":
            username = sys.argv[2]
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            
            logger.info(f"Режим: поиск в профиле @{username}, лимит: {limit}")
            result = finder.find_and_download(username, "profile", limit)
            
        elif mode == "hashtag":
            hashtag = sys.argv[2]
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            
            logger.info(f"Режим: поиск по хэштегу #{hashtag}, лимит: {limit}")
            result = finder.find_and_download(hashtag, "hashtag", limit)
            
        elif mode == "links":
            filename = sys.argv[2]
            
            logger.info(f"Режим: скачивание из файла {filename}")
            video_urls = finder.load_links(filename)
            if video_urls:
                result = finder.download_videos(video_urls)
            else:
                logger.error("Не удалось загрузить ссылки")
                sys.exit(1)
        else:
            logger.error(f"Неизвестный режим: {mode}")
            sys.exit(1)
        
        logger.info(f"\nРезультат: найдено {result.get('found', 0)}, скачано {result.get('downloaded', 0)}")
        
    else:
        # Интерактивный режим
        print("\nВыберите режим:")
        print("1. Поиск в профиле")
        print("2. Поиск по хэштегу")
        print("3. Скачать из сохраненных ссылок")
        
        choice = input("\nВаш выбор (1-3): ").strip()
        
        if choice == "1":
            username = input("Введите имя профиля (без @): ").strip()
            limit = input("Сколько видео найти (по умолчанию 10): ").strip()
            limit = int(limit) if limit else 10
            
            result = finder.find_and_download(username, "profile", limit)
            
        elif choice == "2":
            hashtag = input("Введите хэштег (без #): ").strip()
            limit = input("Сколько видео найти (по умолчанию 10): ").strip()
            limit = int(limit) if limit else 10
            
            result = finder.find_and_download(hashtag, "hashtag", limit)
            
        elif choice == "3":
            print("\nДоступные файлы со ссылками:")
            links_files = list(finder.links_dir.glob("*.txt"))
            if not links_files:
                logger.error("Нет сохраненных файлов со ссылками")
                sys.exit(1)
            
            for i, f in enumerate(links_files, 1):
                print(f"  {i}. {f.name}")
            
            file_num = input("\nВыберите файл (номер): ").strip()
            try:
                filename = links_files[int(file_num) - 1].name
                video_urls = finder.load_links(filename)
                if video_urls:
                    result = finder.download_videos(video_urls)
                else:
                    logger.error("Не удалось загрузить ссылки")
                    sys.exit(1)
            except (ValueError, IndexError):
                logger.error("Неверный номер файла")
                sys.exit(1)
        else:
            logger.error("Неверный выбор")
            sys.exit(1)
        
        logger.info(f"\nГотово! Видео сохранены в: {finder.downloads_dir.absolute()}")


if __name__ == '__main__':
    main()
