"""Вход в Instagram с эмуляцией мобильного устройства."""
import sys
import codecs
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import settings
import instaloader

print("=" * 60)
print("ВХОД В INSTAGRAM (ЭМУЛЯЦИЯ МОБИЛЬНОГО УСТРОЙСТВА)")
print("=" * 60)

username = settings.INSTAGRAM_USERNAME
password = settings.INSTAGRAM_PASSWORD

if not username or not password:
    print("Ошибка: INSTAGRAM_USERNAME и INSTAGRAM_PASSWORD должны быть указаны в .env")
    exit(1)

print(f"\nЛогин: {username}")
print("\nЭтот скрипт эмулирует мобильное устройство для обхода блокировки.")
print("Instagram часто блокирует вход с компьютера, но разрешает с телефона.\n")

try:
    # Создаём instaloader с мобильным User-Agent
    L = instaloader.Instaloader(
        user_agent="Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2134; samsung; SM-G973F; beyond1; exynos9820; en_US; 314665256)",
        download_videos=True,
        download_video_thumbnails=False,
        download_pictures=False,
        quiet=False
    )
    
    # Устанавливаем мобильный User-Agent в сессию
    mobile_user_agent = "Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2134; samsung; SM-G973F; beyond1; exynos9820; en_US; 314665256)"
    L.context._session.headers.update({
        'User-Agent': mobile_user_agent,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'X-IG-App-ID': '567067343352427',
        'X-IG-Device-ID': 'android-' + str(hash(username))[:16],
        'X-IG-Android-ID': 'android-' + str(hash(username))[:16],
    })
    
    print("Настроен мобильный User-Agent")
    print("Пробую войти...\n")
    
    try:
        L.login(username, password)
        print("OK: Успешный вход!")
        
        # Сохраняем сессию
        L.save_session_to_file()
        print("OK: Сессия сохранена!")
        
        # Проверяем
        test_user = L.test_login()
        if test_user:
            print(f"OK: Подтверждено! Пользователь: {test_user}")
            print("\nТеперь можно запускать систему:")
            print("  python test_download.py")
        else:
            print("Предупреждение: Не удалось подтвердить сессию")
            
    except Exception as e:
        error_msg = str(e)
        print(f"Ошибка входа: {error_msg}")
        
        if "Checkpoint" in error_msg or "checkpoint" in error_msg.lower():
            print("\nВсё равно требуется checkpoint.")
            print("\nРешение:")
            print("1. Войдите в Instagram через телефон")
            print("2. Подтвердите что это вы (если требуется)")
            print("3. Попробуйте использовать VPN")
            print("4. Или подождите несколько часов и попробуйте снова")
        else:
            print("\nВозможные решения:")
            print("1. Используйте VPN")
            print("2. Подождите несколько часов")
            print("3. Попробуйте войти через обычный браузер с мобильной версией сайта")
            print("   (m.instagram.com)")

except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
