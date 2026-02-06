"""
Автоматический тест скачивания видео с Instagram.
Использует публичные тестовые URL для проверки всех методов.
"""
import sys
from pathlib import Path
from loguru import logger

# Настройка логирования
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>", level="INFO")

from modules.content_collector.instagram_downloader import (
    download_video_combined,
    download_video_ytdlp,
    extract_shortcode,
)

def main():
    print("\n" + "="*70)
    print("АВТОМАТИЧЕСКИЙ ТЕСТ СКАЧИВАНИЯ ВИДЕО С INSTAGRAM")
    print("="*70)
    
    # Получаем URL от пользователя или используем тестовый
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    else:
        print("\nВведите URL поста Instagram для тестирования.")
        print("Пример: https://www.instagram.com/p/ABC123/")
        print("Или нажмите Enter для использования тестового URL (нужно будет ввести свой)")
        user_input = input("\nURL: ").strip()
        
        if user_input:
            test_url = user_input
        else:
            # Попробуем найти публичный тестовый URL
            print("\nДля автоматического теста нужен реальный URL поста Instagram.")
            print("Пожалуйста, введите URL публичного поста с видео:")
            test_url = input("URL: ").strip()
            
            if not test_url:
                logger.error("URL не указан! Завершение.")
                return
    
    if 'instagram.com' not in test_url:
        logger.error("Неверный URL! Должен содержать instagram.com")
        return
    
    shortcode = extract_shortcode(test_url)
    if not shortcode:
        logger.error("Не удалось извлечь shortcode из URL!")
        return
    
    logger.info(f"Тестируемый URL: {test_url}")
    logger.info(f"Shortcode: {shortcode}")
    
    # Создаем директорию для результатов
    output_dir = Path("test_downloads")
    output_dir.mkdir(exist_ok=True)
    logger.info(f"Результаты будут сохранены в: {output_dir.absolute()}\n")
    
    # Тест 1: Комбинированный метод (рекомендуется)
    logger.info(f"{'='*70}")
    logger.info("ТЕСТ 1: Комбинированный метод (пробует все по очереди)")
    logger.info(f"{'='*70}")
    
    output_path = output_dir / f"{shortcode}_combined.mp4"
    try:
        success = download_video_combined(test_url, str(output_path))
        
        if success and output_path.exists():
            file_size = output_path.stat().st_size
            logger.info(f"[SUCCESS] Видео скачано! Размер: {file_size / 1024 / 1024:.2f} MB")
            logger.info(f"Путь: {output_path.absolute()}")
        else:
            logger.warning("[FAIL] Не удалось скачать видео комбинированным методом")
    except Exception as e:
        logger.error(f"[ERROR] Ошибка: {str(e)}")
    
    # Тест 2: yt-dlp (самый надежный)
    logger.info(f"\n{'='*70}")
    logger.info("ТЕСТ 2: yt-dlp метод (самый надежный)")
    logger.info(f"{'='*70}")
    
    output_path = output_dir / f"{shortcode}_ytdlp.mp4"
    try:
        success = download_video_ytdlp(test_url, str(output_path))
        
        if success and output_path.exists():
            file_size = output_path.stat().st_size
            logger.info(f"[SUCCESS] Видео скачано! Размер: {file_size / 1024 / 1024:.2f} MB")
            logger.info(f"Путь: {output_path.absolute()}")
        else:
            logger.warning("[FAIL] Не удалось скачать видео через yt-dlp")
    except Exception as e:
        logger.error(f"[ERROR] Ошибка: {str(e)}")
    
    logger.info(f"\n{'='*70}")
    logger.info("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    logger.info(f"{'='*70}")
    logger.info(f"Все файлы сохранены в: {output_dir.absolute()}")

if __name__ == '__main__':
    main()
