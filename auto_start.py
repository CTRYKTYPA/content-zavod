"""Полностью автоматический запуск - система сама всё делает."""
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
print("ПОЛНОСТЬЮ АВТОМАТИЧЕСКИЙ ЗАПУСК")
print("=" * 60)
print("\nСистема автоматически войдёт в Instagram и настроит всё.")
print("Ничего делать не нужно - просто ждите.\n")

from config import settings
import instaloader

username = settings.INSTAGRAM_USERNAME
password = settings.INSTAGRAM_PASSWORD

if not username or not password:
    print("Ошибка: INSTAGRAM_USERNAME и INSTAGRAM_PASSWORD должны быть указаны в .env")
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
            print("\nСистема готова! Запускаю тест...\n")
            import subprocess
            subprocess.run([sys.executable, "test_download.py"])
            exit(0)
except:
    pass

print("Сессия не найдена, настраиваю автоматический вход...")

# Шаг 2: Автоматический вход через Selenium
print("\nШаг 2: Автоматический вход через браузер...")

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    import requests
    
    print("Настраиваю браузер...")
    
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15")
    
    # Пробуем использовать webdriver-manager для автоматической загрузки
    try:
        from selenium.webdriver.chrome.service import Service as ChromeService
        from webdriver_manager.chrome import ChromeDriverManager
        
        print("Автоматически загружаю ChromeDriver...")
        driver_path = ChromeDriverManager().install()
        print(f"ChromeDriver загружен: {driver_path}")
        service = ChromeService(driver_path)
    except ImportError:
        # Если webdriver-manager не установлен, ищем вручную
        print("webdriver-manager не установлен, ищу ChromeDriver вручную...")
        driver_path = None
        possible_paths = [
            "chromedriver.exe",
            "chromedriver/chromedriver.exe",
            Path.home() / "chromedriver.exe",
            "C:/chromedriver/chromedriver.exe",
            "C:/Program Files/chromedriver/chromedriver.exe"
        ]
        
        for path in possible_paths:
            if Path(path).exists():
                driver_path = str(Path(path).absolute())
                break
        
        if not driver_path:
            print("ChromeDriver не найден!")
            print("Установите webdriver-manager для автоматической загрузки:")
            print("  pip install webdriver-manager")
            print("Или скачайте вручную с https://chromedriver.chromium.org/")
            raise ImportError("ChromeDriver not found")
        
        service = Service(driver_path)
    
    print(f"Используется ChromeDriver: {driver_path}")
    
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print("Открываю Instagram...")
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(3)
        
        # Вводим логин
        print("Ввожу логин...")
        try:
            username_input = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            username_input.clear()
            username_input.send_keys(username)
            time.sleep(1)
        except TimeoutException:
            print("Не найдено поле логина, пробую другой селектор...")
            username_input = driver.find_element(By.XPATH, "//input[@name='username']")
            username_input.clear()
            username_input.send_keys(username)
            time.sleep(1)
        
        # Вводим пароль
        print("Ввожу пароль...")
        password_input = driver.find_element(By.NAME, "password")
        password_input.clear()
        password_input.send_keys(password)
        time.sleep(1)
        
        # Нажимаем войти
        print("Нажимаю кнопку входа...")
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        
        print("\nОжидаю входа (до 60 секунд)...")
        print("Если появится checkpoint - система автоматически обработает его.")
        
        # Ждём входа или checkpoint
        for i in range(60):
            time.sleep(1)
            
            current_url = driver.current_url
            
            # Проверяем что мы вошли
            if "instagram.com/accounts/login" not in current_url and "challenge" not in current_url.lower():
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
            
            # Проверяем checkpoint
            if "challenge" in current_url.lower() or "checkpoint" in current_url.lower():
                print("Обнаружен checkpoint, ожидаю подтверждения (60 секунд)...")
                print("Если нужно подтвердить через телефон - сделайте это в браузере.")
                
                # Ждём пока пользователь подтвердит
                for j in range(60):
                    time.sleep(1)
                    current_url = driver.current_url
                    
                    if "challenge" not in current_url.lower() and "checkpoint" not in current_url.lower():
                        print("OK: Checkpoint подтверждён!")
                        
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
                
                print("Время ожидания checkpoint истекло.")
                break
        
        print("\nНе удалось автоматически войти.")
        print("Возможные причины:")
        print("1. Требуется подтверждение через телефон")
        print("2. Instagram временно блокирует вход")
        print("3. Неверный пароль")
        
        driver.quit()
        
    except Exception as e:
        print(f"Ошибка автоматизации: {e}")
        if 'driver' in locals():
            driver.quit()
        raise

except ImportError:
    print("Selenium не установлен или ChromeDriver не найден.")
    print("\nУстановите:")
    print("  pip install selenium")
    print("И скачайте ChromeDriver: https://chromedriver.chromium.org/")
    print("\nИспользую альтернативный способ...")
    
    # Альтернатива: пробуем через instaloader с мобильным User-Agent
    print("\nПробую автоматический вход через instaloader...")
    try:
        mobile_user_agent = "Instagram 219.0.0.12.117 Android (29/10; 480dpi; 1080x2134; samsung; SM-G973F; beyond1; exynos9820; en_US; 314665256)"
        L = instaloader.Instaloader(user_agent=mobile_user_agent)
        
        device_id = str(abs(hash(username)))[:16]
        L.context._session.headers.update({
            'X-IG-App-ID': '567067343352427',
            'X-IG-Device-ID': f'android-{device_id}',
            'X-IG-Android-ID': f'android-{device_id}',
        })
        
        print("Вхожу автоматически...")
        L.login(username, password)
        
        print("OK: Успешный вход!")
        L.save_session_to_file()
        print("OK: Сессия сохранена!")
        
        print("\nСистема готова к работе!")
        print("Запускаю тест загрузки...\n")
        import subprocess
        subprocess.run([sys.executable, "test_download.py"])
        exit(0)
        
    except Exception as e:
        print(f"Ошибка автоматического входа: {e}")
        print("\nРешения:")
        print("1. Установите Selenium: pip install selenium")
        print("2. Скачайте ChromeDriver: https://chromedriver.chromium.org/")
        print("3. Или используйте VPN и попробуйте снова")

except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
