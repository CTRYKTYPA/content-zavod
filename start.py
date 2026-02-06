"""Полностью автоматический запуск системы - просто запустите этот файл."""
import sys
import codecs
from pathlib import Path
import time

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("АВТОМАТИЧЕСКИЙ ЗАПУСК СИСТЕМЫ")
print("=" * 60)
print("\nСистема автоматически настроит всё необходимое.")
print("Вам нужно только подтвердить checkpoint в браузере (если появится).\n")

from config import settings
import instaloader

username = settings.INSTAGRAM_USERNAME
password = settings.INSTAGRAM_PASSWORD

if not username:
    print("Ошибка: INSTAGRAM_USERNAME не указан в .env")
    exit(1)

# Шаг 1: Проверяем сохранённую сессию
print("Шаг 1: Проверяю сохранённую сессию...")
try:
    from instaloader.instaloader import get_default_session_filename
    session_file = get_default_session_filename(username)
    if Path(session_file).exists():
        L = instaloader.Instaloader()
        L.load_session_from_file(username)
        test_user = L.test_login()
        if test_user:
            print(f"OK: Сессия работает! Пользователь: {test_user}")
            print("\nСистема готова к работе!")
            print("Запускаю тест загрузки...\n")
            import subprocess
            subprocess.run([sys.executable, "test_download.py"])
            exit(0)
except:
    pass

print("Сессия не найдена или невалидна.")

# Шаг 2: Пробуем автоматически импортировать из браузера
print("\nШаг 2: Пробую импортировать сессию из браузера...")
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
            
            L = instaloader.Instaloader()
            import requests
            session = requests.Session()
            for cookie in cookies:
                session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
            
            L.context._session = session
            test_user = L.test_login()
            if test_user:
                print(f"OK: Импортирована сессия из {browser_name}!")
                L.save_session_to_file()
                print("OK: Сессия сохранена!")
                print("\nСистема готова к работе!")
                print("Запускаю тест загрузки...\n")
                import subprocess
                subprocess.run([sys.executable, "test_download.py"])
                exit(0)
        except:
            continue
except ImportError:
    print("browser-cookie3 не установлен, пропускаю...")
except:
    pass

print("Сессия в браузере не найдена.")

# Шаг 3: Автоматический вход через браузер
if password:
    print("\nШаг 3: Автоматический вход через браузер...")
    print("Откроется браузер, войдите через него.\n")
    
    try:
        # Используем Selenium для автоматизации
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from selenium.common.exceptions import TimeoutException
            
            print("Настраиваю автоматический браузер...")
            
            chrome_options = Options()
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15")
            
            # Пробуем найти ChromeDriver
            driver_path = None
            possible_paths = [
                "chromedriver.exe",
                "chromedriver/chromedriver.exe",
                Path.home() / "chromedriver.exe",
                "C:/chromedriver/chromedriver.exe"
            ]
            
            for path in possible_paths:
                if Path(path).exists():
                    driver_path = str(Path(path).absolute())
                    break
            
            if driver_path:
                print(f"Используется ChromeDriver: {driver_path}")
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                try:
                    print("Открываю Instagram...")
                    driver.get("https://www.instagram.com/accounts/login/")
                    time.sleep(3)
                    
                    # Вводим данные автоматически
                    print("Ввожу данные...")
                    username_input = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.NAME, "username"))
                    )
                    username_input.send_keys(username)
                    
                    password_input = driver.find_element(By.NAME, "password")
                    password_input.send_keys(password)
                    
                    login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
                    login_button.click()
                    
                    print("\nОжидаю входа (30 секунд)...")
                    print("Если появится checkpoint - подтвердите в браузере")
                    
                    # Ждём входа
                    for i in range(30):
                        time.sleep(1)
                        current_url = driver.current_url
                        if "instagram.com/accounts/login" not in current_url:
                            print("OK: Вход выполнен!")
                            
                            # Сохраняем cookies
                            cookies = driver.get_cookies()
                            
                            L = instaloader.Instaloader()
                            session = requests.Session()
                            for cookie in cookies:
                                session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.instagram.com'))
                            
                            L.context._session = session
                            L.save_session_to_file()
                            print("OK: Сессия сохранена!")
                            
                            driver.quit()
                            
                            print("\nСистема готова к работе!")
                            print("Запускаю тест загрузки...\n")
                            import subprocess
                            subprocess.run([sys.executable, "test_download.py"])
                            exit(0)
                    
                    print("\nОжидаю подтверждения checkpoint (60 секунд)...")
                    print("Подтвердите checkpoint в браузере если появился.")
                    
                    # Ждём и периодически проверяем cookies
                    for i in range(60):
                        time.sleep(1)
                        if i % 10 == 0 and i > 0:
                            # Пробуем импортировать cookies
                            try:
                                cookies = driver.get_cookies()
                                if cookies:
                                    L = instaloader.Instaloader()
                                    session = requests.Session()
                                    for cookie in cookies:
                                        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.instagram.com'))
                                    
                                    L.context._session = session
                                    test_user = L.test_login()
                                    if test_user:
                                        print("OK: Сессия работает!")
                                        L.save_session_to_file()
                                        driver.quit()
                                        
                                        print("\nСистема готова к работе!")
                                        print("Запускаю тест загрузки...\n")
                                        import subprocess
                                        subprocess.run([sys.executable, "test_download.py"])
                                        exit(0)
                            except:
                                pass
                    
                    driver.quit()
                    
                    # Пробуем импортировать после подтверждения
                    cookies = driver.get_cookies()
                    L = instaloader.Instaloader()
                    session = requests.Session()
                    for cookie in cookies:
                        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.instagram.com'))
                    
                    L.context._session = session
                    L.save_session_to_file()
                    print("OK: Сессия сохранена!")
                    
                    driver.quit()
                    
                    print("\nСистема готова к работе!")
                    print("Запускаю тест загрузки...\n")
                    import subprocess
                    subprocess.run([sys.executable, "test_download.py"])
                    exit(0)
                
                except Exception as e:
                    print(f"Ошибка автоматизации: {e}")
                    if 'driver' in locals():
                        driver.quit()
            
            else:
                print("ChromeDriver не найден. Использую альтернативный способ...")
        
        except ImportError:
            print("Selenium не установлен. Использую альтернативный способ...")
        
        # Альтернатива: открываем браузер вручную
        print("\nОткрываю браузер для входа...")
        import webbrowser
        webbrowser.open("https://www.instagram.com/accounts/login/")
        
        print("Браузер открыт!")
        print("Войдите в Instagram через браузер.")
        print("Ожидаю входа (60 секунд)...")
        print("Система автоматически проверит сессию каждые 10 секунд.\n")
        
        # Периодически проверяем cookies
        for i in range(60):
            time.sleep(1)
            if i % 10 == 0 and i > 0:
                print(f"Проверяю сессию... ({i} секунд)")
                try:
                    import browser_cookie3
                    cookies = browser_cookie3.chrome(domain_name="instagram.com")
                    
                    if cookies:
                        L = instaloader.Instaloader()
                        session = requests.Session()
                        for cookie in cookies:
                            session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
                        
                        L.context._session = session
                        test_user = L.test_login()
                        if test_user:
                            print(f"OK: Сессия работает! Пользователь: {test_user}")
                            L.save_session_to_file()
                            print("OK: Сессия сохранена!")
                            
                            print("\nСистема готова к работе!")
                            print("Запускаю тест загрузки...\n")
                            import subprocess
                            subprocess.run([sys.executable, "test_download.py"])
                            exit(0)
                except:
                    pass
        
        print("\nВремя ожидания истекло.")
        print("Если вы вошли в Instagram, запустите: python fix_auth_simple.py")
    
    except Exception as e:
        print(f"Ошибка: {e}")

print("\nНе удалось автоматически настроить систему.")
print("Попробуйте:")
print("1. Войти в Instagram через браузер")
print("2. Запустить: python fix_auth_simple.py")
