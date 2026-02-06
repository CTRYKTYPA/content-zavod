"""
Интерактивный тест скачивания видео с Instagram.
Запускает все методы и показывает результаты.
"""
import sys
from pathlib import Path
from typing import Optional
from loguru import logger

# Настройка логирования
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>", level="INFO")

from modules.content_collector.instagram_downloader import (
    download_video_combined,
    download_video_ytdlp,
    download_video_graphql,
    download_video_direct,
    download_video_html_parsing,
    download_video_api_v1,
    download_video_selenium,
    extract_shortcode,
)

def test_single_method(method_name: str, method_func, url: str, output_dir: Path, shortcode: str, proxy: Optional[str] = None):
    """Тестировать один метод."""
    logger.info(f"\n{'='*70}")
    logger.info(f"ТЕСТ: {method_name}")
    logger.info(f"{'='*70}")
    
    output_path = output_dir / f"{shortcode}_{method_name.replace(' ', '_').lower()}.mp4"
    
    try:
        success = method_func(url, str(output_path))
        
        if success and output_path.exists():
            file_size = output_path.stat().st_size
            logger.info(f"[SUCCESS] {method_name}: файл сохранен ({file_size / 1024 / 1024:.2f} MB)")
            logger.info(f"         Путь: {output_path}")
            return True, output_path, file_size
        else:
            logger.warning(f"[FAIL] {method_name}: не удалось скачать")
            if output_path.exists():
                output_path.unlink()  # Удаляем пустой файл
            return False, None, 0
    except Exception as e:
        logger.error(f"[ERROR] {method_name}: {str(e)}")
        if output_path.exists():
            output_path.unlink()
        return False, None, 0

def main():
    print("\n" + "="*70)
    print("ТЕСТИРОВАНИЕ МЕТОДОВ СКАЧИВАНИЯ ВИДЕО С INSTAGRAM")
    print("="*70)
    
    # Получаем URL от пользователя
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("\nВведите URL поста Instagram (например: https://www.instagram.com/p/ABC123/): ").strip()
    
    if not url:
        logger.error("URL не указан!")
        return
    
    # Проверяем формат URL
    if 'instagram.com' not in url:
        logger.error("Неверный URL! Должен содержать instagram.com")
        return
    
    # Извлекаем shortcode
    shortcode = extract_shortcode(url)
    if not shortcode:
        logger.error("Не удалось извлечь shortcode из URL!")
        return
    
    logger.info(f"URL: {url}")
    logger.info(f"Shortcode: {shortcode}")
    
    # Спрашиваем про прокси
    proxy = None
    use_proxy = input("\nИспользовать прокси? (y/n, по умолчанию n): ").strip().lower()
    if use_proxy == 'y':
        proxy = input("Введите прокси (например: http://proxy:port): ").strip()
        if not proxy:
            proxy = None
    
    # Создаем директорию для результатов
    output_dir = Path("test_downloads")
    output_dir.mkdir(exist_ok=True)
    logger.info(f"Результаты будут сохранены в: {output_dir.absolute()}")
    
    # Список методов для тестирования
    methods = [
        ("yt-dlp", download_video_ytdlp),
        ("GraphQL API", download_video_graphql),
        ("Прямые HTTP", download_video_direct),
        ("HTML парсинг", download_video_html_parsing),
        ("API v1", download_video_api_v1),
        ("Selenium", download_video_selenium),
    ]
    
    results = {}
    
    # Тестируем каждый метод
    for method_name, method_func in methods:
        # Проверяем сигнатуру функции для proxy
        import inspect
        sig = inspect.signature(method_func)
        has_proxy = 'proxy' in sig.parameters
        
        if has_proxy and proxy:
            success, file_path, file_size = test_single_method(
                method_name, lambda u, p: method_func(u, p, proxy=proxy), url, output_dir, shortcode, None
            )
        else:
            success, file_path, file_size = test_single_method(
                method_name, method_func, url, output_dir, shortcode, None
            )
        results[method_name] = {
            'success': success,
            'file_path': file_path,
            'file_size': file_size
        }
    
    # Итоговый отчет
    logger.info(f"\n{'='*70}")
    logger.info("ИТОГОВЫЙ ОТЧЕТ")
    logger.info(f"{'='*70}")
    
    successful = [(name, res) for name, res in results.items() if res['success']]
    failed = [(name, res) for name, res in results.items() if not res['success']]
    
    if successful:
        logger.info(f"\n[SUCCESS] Успешные методы ({len(successful)}):")
        for name, res in successful:
            logger.info(f"  - {name:20s} -> {res['file_size'] / 1024 / 1024:.2f} MB")
    
    if failed:
        logger.warning(f"\n[FAIL] Неудачные методы ({len(failed)}):")
        for name, res in failed:
            logger.warning(f"  - {name}")
    
    # Тестируем комбинированный метод
    logger.info(f"\n{'='*70}")
    logger.info("ТЕСТ: Комбинированный метод (пробует все по очереди)")
    logger.info(f"{'='*70}")
    
    output_path = output_dir / f"{shortcode}_combined.mp4"
    try:
        if proxy:
            success = download_video_combined(url, str(output_path), proxy=proxy)
        else:
            success = download_video_combined(url, str(output_path))
        
        if success and output_path.exists():
            file_size = output_path.stat().st_size
            logger.info(f"[SUCCESS] Комбинированный метод: файл сохранен ({file_size / 1024 / 1024:.2f} MB)")
            logger.info(f"         Путь: {output_path}")
        else:
            logger.warning(f"[FAIL] Комбинированный метод: не удалось скачать")
    except Exception as e:
        logger.error(f"[ERROR] Комбинированный метод: {str(e)}")
    
    logger.info(f"\n{'='*70}")
    logger.info("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    logger.info(f"{'='*70}")
    logger.info(f"Все файлы сохранены в: {output_dir.absolute()}")

if __name__ == '__main__':
    main()
