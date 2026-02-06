"""Автоматический вход через Selenium с Яндекс браузером."""
import sys
import codecs
from pathlib import Path
import time

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import settings
import instaloader

print("=" * 60)
print("АВТОМАТИЧЕСКИЙ ВХОД ЧЕРЕЗ SELENIUM")
print("=" * 60)

username = settings.INSTAGRAM_USERNAME
password = settings.INSTAGRAM_PASSWORD

if not username or not password:
    print("Ошибка: INSTAGRAM_USERNAME и INSTAGRAM_PASSWORD должны быть в .env")
    exit(1)

print(f"\nЛогин: {username}")
print("\nОткрываю браузер...")

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    
    # Настройки для Яндекс браузера
    options = webdriver.ChromeOptions()
    
    # Используем обычный Chrome (совместимость с ChromeDriver лучше)
    # Cookies будут работать одинаково для всех браузеров на базе Chromium
    print("Использую Chrome (совместим с ChromeDriver)")
    
    # Мобильный User-Agent (чтобы обойти блокировки)
    options.add_argument("--user-agent=Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36")
    
    # Отключаем автоматизацию
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Отключаем прокси (чтобы избежать ERR_PROXY_CONNECTION_FAILED)
    options.add_argument("--no-proxy-server")
    options.add_argument("--proxy-server='direct://'")
    options.add_argument("--proxy-bypass-list=*")
    
    # Создаём драйвер
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    print("Открываю Instagram...")
    driver.get("https://www.instagram.com/accounts/login/")
    
    time.sleep(3)
    
    # Вводим логин
    print("Ввожу логин...")
    username_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "username"))
    )
    username_input.send_keys(username)
    
    # Вводим пароль
    print("Ввожу пароль...")
    password_input = driver.find_element(By.NAME, "password")
    password_input.send_keys(password)
    
    # Нажимаем войти
    print("Нажимаю войти...")
    login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    login_button.click()
    
    # Ждём загрузки
    print("Жду загрузки...")
    time.sleep(5)
    
    # Проверяем успешность входа
    current_url = driver.get_current_url()
    if "accounts/login" not in current_url:
        print("OK: Вход выполнен!")
        
        # Получаем cookies
        print("Сохраняю cookies...")
        cookies = driver.get_cookies()
        
        # Создаём instaloader
        L = instaloader.Instaloader()
        
        # Импортируем cookies
        import requests
        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.instagram.com'))
        
        L.context._session = session
        
        # Проверяем
        test_user = L.test_login()
        if test_user:
            print(f"OK: Сессия работает! Пользователь: {test_user}")
            
            # Сохраняем
            L.save_session_to_file()
            print("OK: Сессия сохранена!")
            print("\nТеперь можно запускать систему:")
            print("  python test_download.py")
        else:
            print("Ошибка: Сессия не работает")
    else:
        print("Ошибка: Не удалось войти")
        print("Возможные причины:")
        print("  - Неправильный логин/пароль")
        print("  - Требуется подтверждение через телефон")
        print("  - Instagram заблокировал вход")
    
    # Закрываем браузер
    print("\nЗакрываю браузер...")
    driver.quit()
    
except ImportError:
    print("Ошибка: Selenium не установлен")
    print("Установите: pip install selenium webdriver-manager")
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
