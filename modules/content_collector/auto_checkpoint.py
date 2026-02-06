"""Автоматическое прохождение Instagram checkpoint."""
import webbrowser
import time
from typing import Optional
from loguru import logger
import instaloader


def auto_handle_checkpoint(checkpoint_url: str, username: str) -> bool:
    """
    Автоматически обработать checkpoint Instagram.
    
    Args:
        checkpoint_url: URL для подтверждения checkpoint
        username: Имя пользователя Instagram
        
    Returns:
        True если успешно, False иначе
    """
    try:
        logger.info(f"Открываю браузер для подтверждения checkpoint...")
        logger.info(f"URL: {checkpoint_url}")
        
        # Открываем браузер с ссылкой checkpoint
        full_url = f"https://www.instagram.com{checkpoint_url}"
        webbrowser.open(full_url)
        
        logger.info("Браузер открыт. Подтвердите checkpoint в браузере.")
        logger.info("Ожидаю 30 секунд для подтверждения...")
        
        # Ждём пока пользователь подтвердит
        for i in range(30):
            time.sleep(1)
            # Пробуем импортировать сессию из браузера каждые 5 секунд
            if i % 5 == 0 and i > 0:
                if try_import_session_from_browser(username):
                    logger.info("Сессия успешно импортирована после подтверждения checkpoint!")
                    return True
        
        # После ожидания пробуем импортировать ещё раз
        logger.info("Проверяю сессию после ожидания...")
        return try_import_session_from_browser(username)
        
    except Exception as e:
        logger.error(f"Ошибка автоматической обработки checkpoint: {e}")
        return False


def try_import_session_from_browser(username: str) -> bool:
    """Попытаться импортировать сессию из браузера."""
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
                
                # Создаём instaloader для проверки
                L = instaloader.Instaloader()
                
                # Импортируем cookies
                import requests
                session = requests.Session()
                for cookie in cookies:
                    session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
                
                L.context._session = session
                
                # Проверяем что сессия работает
                test_user = L.test_login()
                if test_user:
                    # Сохраняем сессию
                    L.save_session_to_file()
                    logger.info(f"Импортирована сессия из {browser_name} для {test_user}")
                    return True
                    
            except Exception as e:
                logger.debug(f"Не удалось импортировать из {browser_name}: {e}")
                continue
        
        return False
        
    except ImportError:
        logger.debug("browser-cookie3 не установлен")
        return False
    except Exception as e:
        logger.debug(f"Ошибка импорта сессии: {e}")
        return False
