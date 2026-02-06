"""Вход в Instagram через Selenium (автоматизация браузера)."""
import sys
import codecs
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import settings
import time

print("=" * 60)
print("ВХОД В INSTAGRAM ЧЕРЕЗ SELENIUM")
print("=" * 60)

username = settings.INSTAGRAM_USERNAME
password = settings.INSTAGRAM_PASSWORD

if not username or not password:
    print("Ошибка: INSTAGRAM_USERNAME и INSTAGRAM_PASSWORD должны быть указаны в .env")
    exit(1)

print(f"\nЛогин: {username}")
print("\nЭтот скрипт автоматически войдёт в Instagram через браузер.")
print("Установите selenium: pip install selenium")
print("И скачайте ChromeDriver: https://chromedriver.chromium.org/\n")

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    
    print("Настраиваю браузер...")
    
    # Настройки Chrome
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    # Мобильный User-Agent
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36")
    # Отключаем прокси (чтобы избежать ERR_PROXY_CONNECTION_FAILED)
    chrome_options.add_argument("--no-proxy-server")
    chrome_options.add_argument("--proxy-server='direct://'")
    chrome_options.add_argument("--proxy-bypass-list=*")
    
    print("Скачиваю ChromeDriver...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print("\nОткрываю Instagram...")
        driver.get("https://www.instagram.com/accounts/login/")
        
        print("Жду загрузки страницы...")
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
        print("Нажимаю кнопку входа...")
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        
        print("\nОжидаю входа (может потребоваться подтверждение)...")
        print("Если появится checkpoint - подтвердите в браузере")
        print("Если страница не загружается - проверьте VPN")
        
        # Ждём загрузки страницы
        try:
            WebDriverWait(driver, 15).until(
                lambda d: "instagram.com" in d.current_url
            )
        except:
            print("Предупреждение: Страница загружается медленно")
        
        # Ждём либо входа, либо checkpoint
        time.sleep(10)
        
        # Проверяем что мы вошли
        current_url = driver.current_url
        if "instagram.com/accounts/login" not in current_url:
            print("OK: Похоже вход успешен!")
            print(f"Текущий URL: {current_url}")
            
            # Сохраняем cookies
            print("\nСохраняю cookies...")
            cookies = driver.get_cookies()
            
            # Импортируем в instaloader
            import instaloader
            L = instaloader.Instaloader()
            
            import requests
            session = requests.Session()
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.instagram.com'))
            
            L.context._session = session
            
            test_user = L.test_login()
            if test_user:
                print(f"OK: Сессия работает! Пользователь: {test_user}")
                L.save_session_to_file()
                print("OK: Сессия сохранена!")
            else:
                print("Предупреждение: Сессия не работает, но cookies сохранены")
            
            print("\nНажмите Enter чтобы закрыть браузер...")
            input()
        else:
            print("Похоже вход не удался или требуется дополнительное подтверждение")
            print("Проверьте браузер - возможно нужно подтвердить через SMS/email")
            print("\nНажмите Enter когда закончите...")
            input()
    
    finally:
        driver.quit()
        print("Браузер закрыт")

except ImportError:
    print("Ошибка: selenium не установлен")
    print("Установите: pip install selenium")
    print("\nИли используйте: python interactive_login.py")
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
