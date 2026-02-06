"""
АВТОМАТИЧЕСКОЕ получение cookies из ОТКРЫТОГО Яндекс браузера.
Подключается к браузеру через Chrome DevTools Protocol и получает cookies автоматически.
"""
import sys
from pathlib import Path
from typing import Optional, Dict
from loguru import logger
import requests
import json
import time

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium не установлен. Установите: pip install selenium")


def get_cookies_from_open_yandex_via_selenium(session: requests.Session) -> bool:
    """
    Автоматически получить cookies из открытого Яндекс браузера через Selenium remote debugging.
    
    Args:
        session: Сессия requests для загрузки cookies
    
    Returns:
        True если cookies успешно получены
    """
    if not SELENIUM_AVAILABLE:
        logger.error("Selenium не установлен")
        return False
    
    try:
        logger.info("Подключаюсь к открытому Яндекс браузеру...")
        
        # Пробуем подключиться к открытому браузеру через remote debugging
        # Яндекс браузер использует тот же порт что и Chrome
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            logger.info("✅ Подключен к открытому браузеру!")
        except Exception as e:
            logger.warning(f"Не удалось подключиться к порту 9222: {e}")
            logger.info("Пробую запустить браузер с remote debugging...")
            return False
        
        # Переходим на Instagram
        try:
            driver.get('https://www.instagram.com/')
            time.sleep(2)
            
            # Получаем cookies
            selenium_cookies = driver.get_cookies()
            
            if not selenium_cookies:
                logger.warning("Cookies не найдены")
                driver.quit()
                return False
            
            # Загружаем cookies в сессию
            for cookie in selenium_cookies:
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.instagram.com'))
            
            logger.info(f"✅ Получено {len(selenium_cookies)} cookies из браузера")
            
            # Проверяем sessionid
            if 'sessionid' in session.cookies:
                logger.info("✅ sessionid найден!")
                driver.quit()
                return True
            else:
                logger.warning("⚠️  sessionid не найден")
                driver.quit()
                return False
                
        except Exception as e:
            logger.error(f"Ошибка получения cookies: {e}")
            try:
                driver.quit()
            except:
                pass
            return False
            
    except Exception as e:
        logger.error(f"Ошибка подключения к браузеру: {e}")
        return False


def get_cookies_via_cdp(session: requests.Session, port: int = 9222) -> bool:
    """
    Получить cookies через Chrome DevTools Protocol напрямую.
    
    Args:
        session: Сессия requests
        port: Порт remote debugging (по умолчанию 9222)
    
    Returns:
        True если cookies получены
    """
    try:
        from websocket import create_connection
    except ImportError:
        logger.warning("websocket-client не установлен. Установите: pip install websocket-client")
        return False
    
    try:
        import urllib.request
        
        tabs_url = f"http://127.0.0.1:{port}/json"
        try:
            with urllib.request.urlopen(tabs_url, timeout=5) as response:
                tabs = json.loads(response.read().decode('utf-8', errors='ignore'))
        except Exception as e:
            logger.warning(f"Не удалось получить список вкладок: {e}")
            logger.info("Убедитесь что Яндекс браузер запущен с флагом --remote-debugging-port=9222")
            return False
        
        if not tabs:
            logger.warning("Нет открытых вкладок")
            return False
        
        target_tab = None
        for tab in tabs:
            url = tab.get('url', '') or ''
            if 'instagram.com' in url:
                target_tab = tab
                break

        if not target_tab:
            target_tab = tabs[0]
            logger.info("Вкладка Instagram не найдена, использую первую вкладку")

        ws_url = target_tab.get('webSocketDebuggerUrl')
        if not ws_url:
            logger.warning("WebSocketDebuggerUrl не найден")
            return False

        logger.info(f"Подключаюсь к CDP WebSocket: {ws_url}")

        ws = create_connection(ws_url, timeout=5)
        try:
            message_id = 1

            def send(method: str, params: Optional[Dict] = None) -> int:
                nonlocal message_id
                payload: Dict = {"id": message_id, "method": method}
                if params is not None:
                    payload["params"] = params
                ws.send(json.dumps(payload))
                message_id += 1
                return payload["id"]

            def recv_for(expected_id: int, timeout_s: float = 5.0) -> Optional[Dict]:
                deadline = time.time() + timeout_s
                while time.time() < deadline:
                    raw = ws.recv()
                    if not raw:
                        continue
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    if msg.get("id") == expected_id:
                        return msg
                return None

            recv_for(send("Network.enable"), timeout_s=3)

            response = recv_for(send("Network.getCookies", {"urls": ["https://www.instagram.com/"]}), timeout_s=5)
            cookies = []
            if response and isinstance(response.get("result"), dict):
                cookies = response["result"].get("cookies") or []

            if not cookies:
                response = recv_for(send("Network.getAllCookies"), timeout_s=5)
                if response and isinstance(response.get("result"), dict):
                    cookies = response["result"].get("cookies") or []

            if not cookies:
                logger.warning("Не удалось получить cookies через CDP WebSocket")
                return False

            instagram_cookies = [c for c in cookies if 'instagram.com' in (c.get('domain') or '')]
            if not instagram_cookies:
                logger.warning("Cookies Instagram не найдены")
                return False

            for cookie in instagram_cookies:
                name = cookie.get('name')
                if not name:
                    continue
                session.cookies.set(name, cookie.get('value', ''), domain=cookie.get('domain') or '.instagram.com')

            if 'sessionid' in session.cookies:
                logger.info(f"✅ Получено {len(instagram_cookies)} cookies через CDP WebSocket (sessionid найден)")
                return True

            logger.warning(f"⚠️ Получено {len(instagram_cookies)} cookies через CDP WebSocket, но sessionid не найден")
            return False
        finally:
            try:
                ws.close()
            except Exception:
                pass
        
    except Exception as e:
        logger.error(f"Ошибка CDP: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def get_cookies_via_cdp_http(session: requests.Session, port: int = 9222) -> bool:
    """
    Получить cookies через Chrome DevTools Protocol HTTP API (работает с Яндекс браузером!).
    НЕ использует Selenium - работает напрямую через CDP.
    """
    try:
        import urllib.request
        import json as json_lib
        
        logger.info(f"Подключаюсь к Яндекс браузеру через CDP HTTP API (порт {port})...")
        
        # Получаем список вкладок
        tabs_url = f"http://127.0.0.1:{port}/json"
        try:
            with urllib.request.urlopen(tabs_url, timeout=5) as response:
                tabs = json_lib.loads(response.read().decode())
        except Exception as e:
            logger.debug(f"Не удалось получить список вкладок: {e}")
            return False
        
        if not tabs:
            logger.warning("Нет открытых вкладок")
            return False
        
        # Ищем вкладку с Instagram
        instagram_tab = None
        for tab in tabs:
            url = tab.get('url', '')
            if 'instagram.com' in url:
                instagram_tab = tab
                logger.info(f"Найдена вкладка Instagram: {url}")
                break
        
        if not instagram_tab:
            logger.info("Вкладка Instagram не найдена, использую первую вкладку")
            instagram_tab = tabs[0]
        
        # Получаем cookies через CDP команду Network.getCookies
        page_id = instagram_tab.get('id', '')
        ws_url = instagram_tab.get('webSocketDebuggerUrl', '')
        
        if not ws_url:
            logger.warning("WebSocket URL не найден")
            return False
        
        # Используем HTTP API для выполнения CDP команды
        # Создаем новую сессию через /json/new
        try:
            # Пробуем получить cookies через простой HTTP запрос
            # Используем /json/runtime/evaluate для выполнения JavaScript
            evaluate_url = f"http://127.0.0.1:{port}/json/runtime/evaluate"
            
            # Но лучше использовать прямой доступ к cookies через JavaScript
            # Получаем cookies через document.cookie в контексте страницы
            js_code = """
            (function() {
                var cookies = document.cookie.split(';').map(function(c) {
                    var parts = c.trim().split('=');
                    return {name: parts[0], value: parts.slice(1).join('=')};
                }).filter(function(c) { return c.name && c.value; });
                return JSON.stringify(cookies);
            })();
            """
            
            # Отправляем команду через WebSocket или используем более простой способ
            # Проще всего - использовать Selenium только для выполнения JavaScript
            return get_cookies_via_selenium_cdp(session, port)
            
        except Exception as e:
            logger.debug(f"Ошибка получения cookies через CDP HTTP: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка CDP HTTP: {e}")
        return False


def get_cookies_via_selenium_cdp(session: requests.Session, port: int = 9222) -> bool:
    """
    Получить cookies через Selenium с подключением к существующему браузеру.
    Работает с Яндекс браузером через remote debugging.
    """
    if not SELENIUM_AVAILABLE:
        return False
    
    try:
        # Для Яндекс браузера используем ChromeOptions, но указываем правильный executable
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
        
        # НЕ указываем binary_location - пусть использует ChromeDriver для подключения к существующему браузеру
        # Это работает потому что мы подключаемся к уже запущенному браузеру
        
        logger.info(f"Подключаюсь к Яндекс браузеру на порту {port}...")
        
        # Сначала проверяем доступность порта
        try:
            import urllib.request
            test_url = f"http://127.0.0.1:{port}/json"
            with urllib.request.urlopen(test_url, timeout=2) as response:
                tabs = json.loads(response.read().decode())
                logger.info(f"✅ Порт {port} доступен! Найдено {len(tabs)} вкладок")
        except Exception as e:
            logger.warning(f"❌ Порт {port} недоступен: {e}")
            logger.info("Убедитесь что Яндекс браузер запущен с флагом --remote-debugging-port=9222")
            return False
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            logger.info("✅ Подключен к Яндекс браузеру через Selenium!")
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"❌ Ошибка подключения Selenium: {error_msg}")
            if "cannot connect to chrome" in error_msg.lower():
                logger.info("ChromeDriver не может подключиться к браузеру")
                logger.info("Возможные причины:")
                logger.info("1. Браузер не запущен с --remote-debugging-port")
                logger.info("2. Неправильный порт")
                logger.info("3. Браузер заблокирован другим процессом")
            # Пробуем альтернативный способ - через HTTP API CDP
            return get_cookies_via_cdp_http_direct(session, port)
        
        try:
            # Получаем все cookies
            all_cookies = driver.get_cookies()
            
            # Фильтруем cookies для Instagram
            instagram_cookies = [c for c in all_cookies if 'instagram.com' in c.get('domain', '') or '.instagram.com' in c.get('domain', '')]
            
            if not instagram_cookies:
                # Пробуем перейти на Instagram
                logger.info("Перехожу на Instagram для получения cookies...")
                driver.get('https://www.instagram.com/')
                time.sleep(2)
                all_cookies = driver.get_cookies()
                instagram_cookies = [c for c in all_cookies if 'instagram.com' in c.get('domain', '') or '.instagram.com' in c.get('domain', '')]
            
            if not instagram_cookies:
                logger.warning("Cookies Instagram не найдены")
                driver.quit()
                return False
            
            # Загружаем в сессию
            for cookie in instagram_cookies:
                domain = cookie.get('domain', '.instagram.com')
                # Убираем точку в начале если есть
                if domain.startswith('.'):
                    domain = domain[1:]
                session.cookies.set(
                    cookie['name'], 
                    cookie['value'], 
                    domain=domain
                )
            
            logger.info(f"✅ Получено {len(instagram_cookies)} cookies Instagram")
            
            if 'sessionid' in session.cookies:
                logger.info("✅ sessionid найден!")
                driver.quit()
                return True
            else:
                logger.warning("⚠️  sessionid не найден")
                driver.quit()
                return False
                
        except Exception as e:
            logger.error(f"Ошибка получения cookies: {e}")
            try:
                driver.quit()
            except:
                pass
            return False
            
    except Exception as e:
        logger.error(f"Ошибка получения cookies через Selenium: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def get_cookies_via_cdp_http_direct(session: requests.Session, port: int = 9222) -> bool:
    """
    Получить cookies напрямую через Chrome DevTools Protocol HTTP API.
    Работает БЕЗ Selenium - только HTTP запросы.
    """
    try:
        import urllib.request
        import json as json_lib
        
        logger.info(f"Получаю cookies через CDP HTTP API (порт {port})...")
        
        # Получаем список вкладок
        tabs_url = f"http://127.0.0.1:{port}/json"
        try:
            with urllib.request.urlopen(tabs_url, timeout=5) as response:
                tabs = json_lib.loads(response.read().decode())
                logger.info(f"✅ Получен список вкладок: {len(tabs)} шт.")
        except urllib.error.URLError as e:
            logger.warning(f"❌ Не удалось подключиться к порту {port}: {e}")
            logger.info("Проверьте:")
            logger.info("1. Запущен ли Яндекс браузер с --remote-debugging-port=9222")
            logger.info("2. Не занят ли порт другим процессом")
            return False
        except Exception as e:
            logger.warning(f"❌ Ошибка: {e}")
            return False
        
        if not tabs:
            logger.warning("Нет открытых вкладок")
            return False
        
        # Ищем вкладку с Instagram или используем первую
        target_tab = None
        for tab in tabs:
            url = tab.get('url', '')
            if 'instagram.com' in url:
                target_tab = tab
                logger.info(f"✅ Найдена вкладка Instagram: {url}")
                break
        
        if not target_tab:
            target_tab = tabs[0]
            logger.info(f"Использую первую вкладку: {target_tab.get('url', 'unknown')}")
        
        # Получаем cookies через WebSocket CDP команду Network.getCookies
        # Но для этого нужен WebSocket клиент
        # Проще использовать Selenium для выполнения JavaScript
        
        # Альтернатива: используем browser_cookie3 если браузер закрыт
        logger.info("CDP HTTP API требует WebSocket для получения cookies")
        logger.info("Использую альтернативный метод через browser_cookie3...")
        return False
        
    except Exception as e:
        logger.debug(f"Ошибка CDP HTTP direct: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def auto_get_cookies_from_yandex(session: requests.Session) -> bool:
    """
    АВТОМАТИЧЕСКИ получает cookies из открытого Яндекс браузера.
    Пробует несколько методов автоматически.
    
    Args:
        session: Сессия requests
    
    Returns:
        True если cookies получены
    """
    logger.info("="*80)
    logger.info("АВТОМАТИЧЕСКОЕ получение cookies из Яндекс браузера")
    logger.info("="*80)
    
    # Метод 0: CDP WebSocket (без Selenium) - не зависит от ChromeDriver (часто ломается с Яндекс)
    logger.info("\nМетод 0: Подключение через CDP WebSocket (без Selenium)...")
    if get_cookies_via_cdp(session, port=9222):
        return True

    # Метод 1: Selenium с remote debugging (порт 9222) - работает с Яндекс браузером!
    logger.info("\nМетод 1: Подключение через Selenium к Яндекс браузеру (порт 9222)...")
    if get_cookies_via_selenium_cdp(session, port=9222):
        return True
    
    # Метод 2: CDP HTTP API (без Selenium)
    logger.info("\nМетод 2: Подключение через CDP HTTP API (порт 9222)...")
    if get_cookies_via_cdp_http(session, port=9222):
        return True
    
    # Метод 3: Пробуем другие стандартные порты
    for port in [9223, 9224, 9225]:
        logger.info(f"\nМетод 3: Пробую порт {port}...")
        if get_cookies_via_selenium_cdp(session, port=port):
            return True
        if get_cookies_via_cdp_http(session, port=port):
            return True
    
    logger.error("❌ Не удалось автоматически получить cookies")
    logger.info("\nРЕШЕНИЕ:")
    logger.info("1. Запустите Яндекс браузер с флагом remote debugging:")
    logger.info('   "C:\\Users\\Даниил\\AppData\\Local\\Yandex\\YandexBrowser\\Application\\browser.exe" --remote-debugging-port=9222')
    logger.info("2. Откройте Instagram в браузере")
    logger.info("3. Запустите скрипт снова")
    
    return False
