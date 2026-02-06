"""Проверка зависимостей для скачивания Instagram видео."""
import sys

dependencies = {
    'requests': 'requests',
    'yt_dlp': 'yt-dlp',
    'bs4': 'beautifulsoup4',
    'selenium': 'selenium',
    'browser_cookie3': 'browser-cookie3',
    'webdriver_manager': 'webdriver-manager',
}

print("Проверка зависимостей для скачивания Instagram видео:\n")
print("=" * 60)

all_ok = True
for module_name, package_name in dependencies.items():
    try:
        __import__(module_name)
        print(f"[OK] {package_name:30s} - установлен")
    except ImportError:
        print(f"[FAIL] {package_name:30s} - НЕ УСТАНОВЛЕН")
        all_ok = False

print("=" * 60)

# Проверка user agents
try:
    from modules.content_collector.instagram_downloader import load_user_agents
    ua = load_user_agents()
    print(f"\n[OK] User agents: загружено {len(ua)} из useragents.txt")
except Exception as e:
    print(f"\n[FAIL] Ошибка загрузки user agents: {e}")
    all_ok = False

if all_ok:
    print("\n[OK] Все зависимости установлены! Можно запускать тесты.")
    sys.exit(0)
else:
    print("\n[FAIL] Некоторые зависимости отсутствуют. Установите их:")
    print("pip install yt-dlp beautifulsoup4 selenium webdriver-manager browser-cookie3")
    sys.exit(1)
