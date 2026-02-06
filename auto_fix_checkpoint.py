"""Автоматическое исправление checkpoint Instagram."""
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
import webbrowser
import time

print("=" * 60)
print("АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ CHECKPOINT INSTAGRAM")
print("=" * 60)

username = settings.INSTAGRAM_USERNAME
password = settings.INSTAGRAM_PASSWORD

if not username:
    print("Ошибка: INSTAGRAM_USERNAME не указан в .env")
    exit(1)

print(f"\nЛогин: {username}")

# Пробуем войти
print("\nПробую войти в Instagram...")
L = instaloader.Instaloader()

try:
    L.login(username, password)
    print("OK: Успешный вход!")
    L.save_session_to_file()
    print("OK: Сессия сохранена!")
    exit(0)
except Exception as e:
    error_msg = str(e)
    if "Checkpoint required" in error_msg or "checkpoint" in error_msg.lower():
        print("\nInstagram требует checkpoint.")
        
        # Извлекаем URL
        checkpoint_url = None
        if "/auth_platform/" in error_msg:
            start = error_msg.find("/auth_platform/")
            end = error_msg.find(" ", start)
            if end == -1:
                end = error_msg.find("\n", start)
            if end == -1:
                end = len(error_msg)
            checkpoint_url = error_msg[start:end].strip()
        
        if checkpoint_url:
            print(f"\nОткрываю браузер для подтверждения checkpoint...")
            print(f"URL: https://www.instagram.com{checkpoint_url}")
            
            # Открываем браузер
            webbrowser.open(f"https://www.instagram.com{checkpoint_url}")
            
            print("\nБраузер открыт!")
            print("Инструкция:")
            print("1. Подтвердите что это вы в открывшемся окне браузера")
            print("2. Подождите пока закроется это окно")
            print("3. Система автоматически импортирует сессию")
            
            # Ждём и пробуем импортировать
            print("\nОжидаю подтверждения (30 секунд)...")
            
            for i in range(30):
                time.sleep(1)
                if i % 5 == 0 and i > 0:
                    # Пробуем импортировать из браузера
                    try:
                        import browser_cookie3
                        
                        browsers = [
                            ("Chrome", lambda: browser_cookie3.chrome(domain_name="instagram.com")),
                            ("Firefox", lambda: browser_cookie3.firefox(domain_name="instagram.com")),
                            ("Edge", lambda: browser_cookie3.edge(domain_name="instagram.com")),
                        ]
                        
                        for browser_name, get_cookies in browsers:
                            try:
                                cookies = get_cookies()
                                if not cookies:
                                    continue
                                
                                session = instaloader.Instaloader()
                                import requests
                                req_session = requests.Session()
                                for cookie in cookies:
                                    req_session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
                                
                                session.context._session = req_session
                                
                                test_user = session.test_login()
                                if test_user:
                                    session.save_session_to_file()
                                    print(f"\nOK: Сессия импортирована из {browser_name}!")
                                    print(f"Пользователь: {test_user}")
                                    print("\nТеперь можно запускать систему!")
                                    exit(0)
                            except:
                                continue
                    except ImportError:
                        print("\nОшибка: browser-cookie3 не установлен")
                        print("Установите: pip install browser-cookie3")
                        exit(1)
                    except Exception as e:
                        continue
            
            print("\nНе удалось автоматически импортировать сессию.")
            print("Попробуйте запустить: python simple_auth.py")
        else:
            print("\nНе удалось извлечь URL checkpoint из ошибки")
            print("Попробуйте:")
            print("1. Войдите в Instagram через браузер")
            print("2. Запустите: python simple_auth.py")
    else:
        print(f"\nОшибка: {e}")
