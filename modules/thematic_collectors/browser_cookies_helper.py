"""
Помощник для загрузки cookies из браузера вместо логина через Selenium.
Обходит блокировку Instagram на логин с нового браузера.
"""
import os
import time
from pathlib import Path
from typing import Optional
import requests
from loguru import logger

try:
    import browser_cookie3
    BROWSER_COOKIE3_AVAILABLE = True
except ImportError:
    BROWSER_COOKIE3_AVAILABLE = False
    logger.warning("browser_cookie3 не установлен. Установите: pip install browser_cookie3")

# Импортируем автоматическое получение cookies
try:
    from modules.thematic_collectors.auto_cookies_yandex import auto_get_cookies_from_yandex
    AUTO_COOKIES_AVAILABLE = True
except ImportError:
    AUTO_COOKIES_AVAILABLE = False

# Импортируем автоматическую расшифровку cookies из базы
try:
    from modules.thematic_collectors.yandex_cookies_decrypt import get_yandex_cookies_from_db
    YANDEX_DECRYPT_AVAILABLE = True
except ImportError:
    YANDEX_DECRYPT_AVAILABLE = False


def load_cookies_from_browser(
    session: requests.Session,
    browser: str = "chrome",
    cookie_file: Optional[str] = None
) -> bool:
    """
    Загрузить cookies Instagram из реального браузера.
    АВТОМАТИЧЕСКИ пробует получить cookies из открытого браузера для Яндекс.
    
    Args:
        session: Сессия requests для загрузки cookies
        browser: Браузер ('chrome', 'firefox', 'edge', 'yandex')
        cookie_file: Путь к файлу cookies (опционально)
    
    Returns:
        True если cookies успешно загружены
    """
    # Для Яндекс браузера - пробуем несколько методов автоматически
    if browser == 'yandex':
        # Метод 1: Автоматическая расшифровка из базы (РАБОТАЕТ ДАЖЕ ЕСЛИ БРАУЗЕР ОТКРЫТ!)
        if YANDEX_DECRYPT_AVAILABLE:
            logger.info("🔄 Метод 1: Автоматическая расшифровка cookies из базы данных...")
            if get_yandex_cookies_from_db(session):
                logger.info("✅✅✅ Cookies автоматически расшифрованы из базы данных!")
                return True
            logger.info("Расшифровка из базы не сработала, пробую другие методы...")
        
        # Метод 2: Remote debugging (если браузер запущен с флагом)
        if AUTO_COOKIES_AVAILABLE:
            logger.info("🔄 Метод 2: Подключение через remote debugging...")
            if auto_get_cookies_from_yandex(session):
                logger.info("✅ Cookies автоматически получены через remote debugging!")
                return True
            logger.info("Remote debugging не сработал, пробую стандартный метод...")
    
    if not BROWSER_COOKIE3_AVAILABLE:
        logger.error("[ERROR] browser_cookie3 не установлен. Установите: pip install browser_cookie3")
        return False
    
    try:
        logger.info(f"Загружаю cookies Instagram из браузера: {browser}")
        
        # Поддерживаемые браузеры
        browser_loaders = {
            'chrome': browser_cookie3.chrome,
            'firefox': browser_cookie3.firefox,
            'edge': browser_cookie3.edge,
            'yandex': lambda **kwargs: browser_cookie3.chrome(**kwargs),  # Яндекс использует Chrome движок
        }
        
        if browser not in browser_loaders:
            logger.error(f"[ERROR] Неподдерживаемый браузер: {browser}")
            logger.info(f"Поддерживаемые: {', '.join(browser_loaders.keys())}")
            return False
        
        loader = browser_loaders[browser]
        
        # Загружаем cookies
        if cookie_file:
            logger.info(f"Использую файл cookies: {cookie_file}")
            cookies = loader(domain_name="instagram.com", cookie_file=cookie_file)
        else:
            # Для Яндекс браузера указываем путь к профилю
            if browser == 'yandex':
                yandex_profile = Path(os.getenv("LOCALAPPDATA")) / "Yandex" / "YandexBrowser" / "User Data" / "Default"
                cookies_file = yandex_profile / "Network" / "Cookies"
                
                if cookies_file.exists():
                    logger.info(f"Найден файл cookies Яндекс браузера: {cookies_file}")
                    
                    # Пробуем несколько способов чтения cookies
                    cookies = None
                    
                    # Способ 1: Прямое чтение через browser_cookie3 (может не работать если браузер открыт)
                    try:
                        logger.debug("Пробую прямое чтение cookies...")
                        cookies = loader(domain_name="instagram.com", cookie_file=str(cookies_file))
                        cookies_list_test = list(cookies)
                        if cookies_list_test:
                            logger.info("[OK] Прямое чтение сработало!")
                    except Exception as e:
                        logger.debug(f"Прямое чтение не сработало: {e}")
                        cookies = None
                    
                    # Способ 2: Копирование файла (обход блокировки)
                    if not cookies:
                        import tempfile
                        import shutil
                        import time
                        
                        # Пробуем несколько раз с задержкой
                        for attempt in range(3):
                            try:
                                temp_cookies = Path(tempfile.gettempdir()) / f"yandex_cookies_{os.getpid()}_{attempt}"
                                logger.debug(f"Попытка {attempt + 1}/3: копирую файл cookies...")
                                
                                # Небольшая задержка перед копированием
                                time.sleep(0.5)
                                
                                shutil.copy2(cookies_file, temp_cookies)
                                logger.debug("Файл cookies скопирован")
                                
                                # Пробуем прочитать
                                cookies = loader(domain_name="instagram.com", cookie_file=str(temp_cookies))
                                cookies_list_test = list(cookies)
                                
                                if cookies_list_test:
                                    logger.info(f"[OK] Копирование сработало на попытке {attempt + 1}!")
                                    # Удаляем временный файл
                                    try:
                                        temp_cookies.unlink(missing_ok=True)
                                    except:
                                        pass
                                    break
                                else:
                                    # Удаляем временный файл и пробуем снова
                                    try:
                                        temp_cookies.unlink(missing_ok=True)
                                    except:
                                        pass
                                    
                            except PermissionError:
                                logger.debug(f"Попытка {attempt + 1}: файл заблокирован, жду...")
                                time.sleep(1)
                                continue
                            except Exception as e:
                                logger.debug(f"Попытка {attempt + 1} не удалась: {e}")
                                if attempt < 2:
                                    time.sleep(1)
                                    continue
                                else:
                                    logger.warning("Все попытки копирования не удались")
                                    break
                    
                    # Способ 3: Чтение через SQLite напрямую с копированием (работает даже если браузер открыт)
                    if not cookies:
                        try:
                            logger.debug("Пробую чтение через SQLite с копированием...")
                            import sqlite3
                            import tempfile
                            import shutil
                            
                            # Копируем базу во временную папку для чтения
                            temp_db = Path(tempfile.gettempdir()) / f"yandex_cookies_db_{os.getpid()}.db"
                            
                            # Пробуем скопировать несколько раз
                            copied = False
                            for attempt in range(5):
                                try:
                                    time.sleep(0.3)  # Небольшая задержка
                                    shutil.copy2(cookies_file, temp_db)
                                    copied = True
                                    logger.debug(f"База скопирована на попытке {attempt + 1}")
                                    break
                                except PermissionError:
                                    if attempt < 4:
                                        logger.debug(f"Попытка {attempt + 1}: файл заблокирован, жду...")
                                        time.sleep(0.5)
                                        continue
                                    else:
                                        raise
                            
                            if copied:
                                # Читаем из копии
                                conn = sqlite3.connect(str(temp_db))
                                cursor = conn.cursor()
                                
                                # Читаем cookies для instagram.com
                                cursor.execute("""
                                    SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
                                    FROM cookies
                                    WHERE host_key LIKE '%instagram.com%'
                                """)
                                
                                cookie_rows = cursor.fetchall()
                                conn.close()
                                
                                # Удаляем временную копию
                                try:
                                    temp_db.unlink(missing_ok=True)
                                except:
                                    pass
                                
                                if cookie_rows:
                                    logger.info(f"[OK] Найдено {len(cookie_rows)} cookies через SQLite!")
                                    # Создаем фиктивные cookie объекты для browser_cookie3 формата
                                    class FakeCookie:
                                        def __init__(self, name, value, domain):
                                            self.name = name
                                            self.value = value
                                            self.domain = domain
                                    
                                    cookies = [FakeCookie(row[0], row[1], row[2]) for row in cookie_rows]
                                else:
                                    logger.warning("SQLite: cookies не найдены в базе")
                            else:
                                logger.warning("Не удалось скопировать базу cookies")
                                
                        except Exception as e:
                            logger.debug(f"SQLite чтение не сработало: {e}")
                            cookies = None
                    
                    # Если ничего не сработало
                    if not cookies:
                        logger.warning("Не удалось прочитать cookies из Яндекс браузера")
                        logger.warning("Попробуйте:")
                        logger.warning("  1. Закрыть Яндекс браузер полностью")
                        logger.warning("  2. Подождать 2-3 секунды")
                        logger.warning("  3. Запустить снова")
                        return False
                else:
                    logger.warning("Файл cookies Яндекс браузера не найден")
                    return False
            else:
                cookies = loader(domain_name="instagram.com")
        
        cookies_list = list(cookies)
        
        if not cookies_list:
            logger.warning("[WARN] Cookies Instagram не найдены в браузере")
            logger.warning("[WARN] Убедитесь что:")
            logger.warning("  1. Браузер закрыт (или закройте его)")
            logger.warning("  2. Вы залогинены на instagram.com в этом браузере")
            return False
        
        logger.info(f"[OK] Найдено {len(cookies_list)} cookies Instagram")
        
        # Загружаем cookies в сессию
        for cookie in cookies_list:
            session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
        
        # Проверяем наличие важных cookies
        important_cookies = ['sessionid', 'csrftoken', 'ds_user_id']
        found_cookies = [name for name in important_cookies if name in session.cookies]
        
        if 'sessionid' in session.cookies:
            logger.info("[OK] sessionid cookie найден - авторизация должна работать!")
            logger.debug(f"Найдено важных cookies: {', '.join(found_cookies)}")
            return True
        else:
            logger.warning("[WARN] sessionid cookie не найден")
            logger.warning(f"Найдено cookies: {', '.join(found_cookies)}")
            logger.warning("Сессия может не работать. Убедитесь что вы залогинены в браузере.")
            return False
            
    except Exception as e:
        logger.error(f"[ERROR] Ошибка загрузки cookies: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def load_cookies_from_instaloader_session(
    session: requests.Session,
    username: str
) -> bool:
    """
    Загрузить cookies из сохраненной сессии instaloader.
    
    Args:
        session: Сессия requests
        username: Имя пользователя Instagram
    
    Returns:
        True если сессия загружена
    """
    try:
        import instaloader
        from instaloader.instaloader import get_default_session_filename
        
        # Получаем путь к файлу сессии
        session_file = get_default_session_filename(username)
        
        if not Path(session_file).exists():
            logger.warning(f"[WARN] Файл сессии не найден: {session_file}")
            return False
        
        logger.info(f"Загружаю сессию instaloader из: {session_file}")
        
        # Создаем instaloader и загружаем сессию
        L = instaloader.Instaloader()
        L.load_session_from_file(username)
        
        # Копируем cookies из instaloader в нашу сессию
        for cookie in L.context._session.cookies:
            session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
        
        # Проверяем
        if 'sessionid' in session.cookies:
            logger.info("[OK] Сессия instaloader загружена успешно!")
            return True
        else:
            logger.warning("[WARN] Сессия instaloader не содержит sessionid")
            return False
            
    except Exception as e:
        logger.error(f"[ERROR] Ошибка загрузки сессии instaloader: {e}")
        return False


def test_session(session: requests.Session) -> Optional[str]:
    """
    Проверить работоспособность сессии.
    
    Args:
        session: Сессия requests
    
    Returns:
        Username если сессия работает, None если нет
    """
    try:
        # Пробуем получить информацию о текущем пользователе
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-IG-App-ID': '936619743392459',
        }
        
        response = session.get(
            'https://www.instagram.com/api/v1/web/data/shared_data/',
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                # Пробуем извлечь username из разных мест
                if 'config' in data:
                    viewer = data['config'].get('viewer')
                    if viewer:
                        username = viewer.get('username')
                        if username:
                            logger.info(f"[OK] Сессия работает! Пользователь: {username}")
                            return username
            except:
                pass
        
        # Альтернативный способ - через главную страницу
        response = session.get('https://www.instagram.com/', headers=headers, timeout=10)
        if response.status_code == 200:
            # Проверяем наличие sessionid
            if 'sessionid' in session.cookies:
                logger.info("[OK] Сессия работает (есть sessionid cookie)")
                return "unknown"  # Не можем определить username, но сессия работает
        
        logger.warning("[WARN] Не удалось проверить сессию")
        return None
        
    except Exception as e:
        logger.error(f"[ERROR] Ошибка проверки сессии: {e}")
        return None
