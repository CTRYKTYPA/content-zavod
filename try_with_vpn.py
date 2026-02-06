"""Попытка входа с VPN/прокси."""
import sys
import codecs
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import settings
import instaloader

print("=" * 60)
print("ВХОД С VPN/ПРОКСИ")
print("=" * 60)

username = settings.INSTAGRAM_USERNAME
password = settings.INSTAGRAM_PASSWORD
proxy = settings.INSTAGRAM_PROXY

if not username or not password:
    print("Ошибка: INSTAGRAM_USERNAME и INSTAGRAM_PASSWORD должны быть указаны в .env")
    exit(1)

print(f"\nЛогин: {username}")
if proxy:
    print(f"Прокси: {proxy}")
else:
    print("Прокси: не указан")
    print("\nДля использования прокси добавьте в .env:")
    print("INSTAGRAM_PROXY=http://proxy.example.com:8080")

print("\nПробую войти с мобильным User-Agent...\n")

try:
    mobile_user_agent = "Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2134; samsung; SM-G973F; beyond1; exynos9820; en_US; 314665256)"
    L = instaloader.Instaloader(
        user_agent=mobile_user_agent,
        download_videos=True,
        download_video_thumbnails=False,
        download_pictures=False,
        quiet=False
    )
    
    # Настройка прокси если указан
    if proxy:
        proxies = {
            'http': proxy,
            'https': proxy
        }
        L.context._session.proxies.update(proxies)
        print(f"Используется прокси: {proxy}")
    
    # Мобильные заголовки
    device_id = str(abs(hash(username)))[:16]
    L.context._session.headers.update({
        'X-IG-App-ID': '567067343352427',
        'X-IG-Device-ID': f'android-{device_id}',
        'X-IG-Android-ID': f'android-{device_id}',
    })
    
    print("Пробую войти...")
    L.login(username, password)
    
    print("OK: Успешный вход!")
    L.save_session_to_file()
    print("OK: Сессия сохранена!")
    
    test_user = L.test_login()
    if test_user:
        print(f"OK: Подтверждено! Пользователь: {test_user}")
        print("\nТеперь можно запускать систему:")
        print("  python test_download.py")

except Exception as e:
    error_msg = str(e)
    print(f"Ошибка: {error_msg}")
    
    if "Wrong password" in error_msg:
        print("\nInstagram временно блокирует вход.")
        print("\nРешения:")
        print("1. Включите VPN и попробуйте снова")
        print("2. Подождите 2-4 часа")
        print("3. Войдите через телефон, затем через браузер на компьютере")
        print("4. Используйте мобильную версию: m.instagram.com")
    elif "Checkpoint" in error_msg:
        print("\nТребуется checkpoint.")
        print("Подтвердите через телефон или браузер.")
    else:
        print("\nПопробуйте:")
        print("1. Включить VPN")
        print("2. Подождать несколько часов")
        print("3. Использовать другой IP")
