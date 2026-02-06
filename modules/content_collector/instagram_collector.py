"""Сборщик контента из Instagram."""
import sys
import os
import time
import random
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

# Загрузка User-Agent из файла для ротации
_USER_AGENTS_CACHE = None

def _load_user_agents() -> List[str]:
    """Загрузить User-Agent строки из файла и отфильтровать только современные десктопные."""
    global _USER_AGENTS_CACHE
    if _USER_AGENTS_CACHE is not None:
        return _USER_AGENTS_CACHE
    
    useragents_file = Path(__file__).parent.parent.parent / "useragents.txt"
    user_agents = []
    max_lines = 1000  # Ограничиваем обработку первыми 1000 строками для скорости
    max_agents = 200  # Максимум User-Agent для ротации
    
    if useragents_file.exists():
        try:
            with open(useragents_file, 'r', encoding='utf-8', errors='ignore') as f:
                line_count = 0
                for line in f:
                    line_count += 1
                    if line_count > max_lines:  # Останавливаемся после первых 1000 строк
                        break
                    if len(user_agents) >= max_agents:  # Достаточно User-Agent
                        break
                    
                    line = line.strip()
                    if not line or len(line) < 30:
                        continue
                    
                    # Упрощённая фильтрация: любые десктопные Chrome/Firefox (не мобильные)
                    if ('Chrome/' in line or 'Firefox/' in line) and 'Mobile' not in line and 'Android' not in line:
                        # Проверяем что это действительно браузерный User-Agent
                        if 'Windows' in line or 'Macintosh' in line or 'Linux' in line or 'X11' in line:
                            user_agents.append(line)
        except Exception as e:
            logger.warning(f"Не удалось загрузить User-Agent из файла: {e}")
    
    # Если не нашли в файле или файла нет - используем дефолтные современные
    if not user_agents:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]
    
    _USER_AGENTS_CACHE = user_agents
    logger.info(f"Загружено {len(user_agents)} User-Agent строк для ротации")
    return user_agents

# Добавляем путь к instaloader
instaloader_path = Path(__file__).parent.parent.parent / "instaloader-master"
sys.path.insert(0, str(instaloader_path))

# Импортируем instaloader
try:
    import instaloader
    from instaloader import Post, Profile, Hashtag
    # Импортируем функцию для получения пути к сессии
    try:
        from instaloader.instaloader import get_default_session_filename
    except ImportError:
        # Альтернативный способ - создаём функцию сами
        def get_default_session_filename(username: str) -> str:
            """Получить путь к файлу сессии."""
            import tempfile
            import getpass
            if os.name == 'nt':  # Windows
                localappdata = os.getenv("LOCALAPPDATA")
                if localappdata:
                    configdir = os.path.join(localappdata, "Instaloader")
                else:
                    configdir = os.path.join(tempfile.gettempdir(), ".instaloader-" + getpass.getuser())
            else:  # Unix
                configdir = os.path.join(os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "instaloader")
            os.makedirs(configdir, exist_ok=True)
            return os.path.join(configdir, f"session-{username}")
except ImportError:
    # Если instaloader не установлен, пробуем установить из папки
    import subprocess
    import sys
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", str(instaloader_path)])
        import instaloader
        from instaloader import Post, Profile, Hashtag
        from instaloader.instaloader import get_default_session_filename
    except Exception as e:
        logger.error(f"Не удалось импортировать instaloader: {e}")
        raise

from .base_collector import BaseCollector
from database.models import ContentSource, VideoStatus
from config import settings


class InstagramCollector(BaseCollector):
    """Сборщик видео из Instagram."""
    
    def __init__(self, source: ContentSource, username: Optional[str] = None, password: Optional[str] = None):
        """
        Инициализация сборщика Instagram.
        
        Args:
            source: Источник контента
            username: Логин Instagram (опционально, переопределяет настройки)
            password: Пароль Instagram (опционально, переопределяет настройки)
        """
        super().__init__(source)
        # Используем реальный браузерный User-Agent из файла для ротации
        # Это критично - мобильный User-Agent Instagram приложения выдает автоматизацию!
        # Ротация User-Agent помогает избежать детекции
        user_agents_list = _load_user_agents()
        browser_user_agent = random.choice(user_agents_list)
        logger.debug(f"Используется User-Agent: {browser_user_agent[:80]}...")
        
        # Сохраняем список для ротации между запросами
        self.user_agents_pool = user_agents_list
        self.current_user_agent = browser_user_agent
        
        # НЕ создаём instaloader - используем только Selenium + yt-dlp
        # self.loader больше не используется, но оставляем для совместимости
        self.loader = None
        
        # Настройка задержек для имитации человека (сильно увеличено для избежания rate limiting)
        self.min_delay = 15.0  # Минимальная задержка между запросами (секунды) - сильно увеличено
        self.max_delay = 30.0  # Максимальная задержка между запросами (секунды) - сильно увеличено
        self.post_delay = (20.0, 40.0)  # Задержка между обработкой постов - сильно увеличено
        
        # Реалистичные заголовки браузера для веб-версии Instagram
        # КРИТИЧНО: x-ig-app-id должен быть для веб-версии (936619743392459), а не мобильной!
        # Для анонимного доступа используем минимальные заголовки
        self.loader.context._session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'x-ig-app-id': '936619743392459',  # Веб-версия Instagram, не мобильная!
            'Referer': 'https://www.instagram.com/',
            'Origin': 'https://www.instagram.com',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        })
        
        # Настройка прокси с ротацией (только если прокси указан в настройках)
        # С ротацией User-Agent прокси может быть не обязателен
        # Сначала проверяем системные переменные окружения (для VPN типа Hiddify)
        system_proxy = os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY') or os.getenv('http_proxy') or os.getenv('https_proxy')
        
        # Если есть много User-Agent для ротации, можно работать без прокси
        use_proxy = True  # По умолчанию используем прокси если есть
        if len(user_agents_list) > 50:  # Если много User-Agent, можно попробовать без прокси
            logger.info(f"Обнаружено {len(user_agents_list)} User-Agent - ротация может заменить прокси")
            # Можно отключить прокси, если пользователь хочет
            # use_proxy = False
        
        if use_proxy:
            if system_proxy:
                logger.info(f"Обнаружен системный прокси/VPN: {system_proxy.split('@')[-1] if '@' in system_proxy else system_proxy}")
                self._setup_proxy(system_proxy)
            elif settings.INSTAGRAM_PROXY or settings.PROXY_LIST:
                try:
                    from .proxy_rotator import get_proxy_rotator
                    proxy_rotator = get_proxy_rotator()
                    if proxy_rotator.has_proxies():
                        proxy = proxy_rotator.get_next_proxy()
                        if proxy:
                            self._setup_proxy(proxy)
                            # Маскируем пароль в логах
                            display_proxy = proxy.split('@')[-1] if '@' in proxy else proxy
                            logger.info(f"Используется прокси из настроек: {display_proxy}")
                except Exception as e:
                    logger.warning(f"Не удалось настроить прокси: {e}. Работаем без прокси.")
            else:
                # Пробуем автоматически определить локальный прокси Hiddify (127.0.0.1:8964)
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex(('127.0.0.1', 8964))
                    sock.close()
                    if result == 0:  # Порт открыт
                        hiddify_proxy = "http://127.0.0.1:8964"
                        logger.info("Обнаружен локальный прокси Hiddify на порту 8964")
                        self._setup_proxy(hiddify_proxy)
                except Exception:
                    pass  # Игнорируем ошибки проверки
        else:
            logger.info("Прокси отключен - используем только ротацию User-Agent")
        
        # Определяем какой аккаунт использовать
        instagram_username = username
        instagram_password = password
        
        # Если указан конкретный аккаунт для источника - используем его
        if hasattr(source, 'instagram_account_id') and source.instagram_account_id:
            from database.models import Account
            account = source.instagram_account
            if account and account.instagram_session_username:
                instagram_username = account.instagram_session_username
                # Пароль берём из credentials если есть
                if account.credentials and isinstance(account.credentials, dict):
                    instagram_password = account.credentials.get("password")
        
        # Если не указан - используем дефолтный из настроек
        if not instagram_username:
            instagram_username = settings.INSTAGRAM_USERNAME
        if not instagram_password:
            instagram_password = settings.INSTAGRAM_PASSWORD
        
        # НЕ используем instaloader авторизацию - работаем полностью через Selenium/yt-dlp
        logger.info(f"Работаю БЕЗ instaloader для профиля {self.source_value} (использую только Selenium/yt-dlp)")
        # Не вызываем _login, не используем instaloader вообще
    
    def _try_import_browser_session(self, username: str) -> bool:
        """Попытаться импортировать сессию из браузера (не используется, т.к. не используем instaloader)."""
        # Больше не используется - работаем через Selenium/yt-dlp
        return False
    
    def _setup_proxy(self, proxy_url: str):
        """Настроить прокси для Instagram запросов."""
        # Просто сохраняем прокси - используется в Selenium/yt-dlp
        self.proxy_url = proxy_url
        logger.info(f"Настроен прокси: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url}")
    
    def _login(self, username: Optional[str], password: Optional[str]):
        """Авторизация в Instagram (не используется, т.к. работаем через Selenium/yt-dlp)."""
        # Больше не используется - работаем через Selenium/yt-dlp без авторизации
        logger.debug("Метод _login больше не используется (работаем через Selenium/yt-dlp)")
        return
    
    def _rotate_user_agent(self, force: bool = False):
        """
        Ротация User-Agent для избежания детекции.
        
        Args:
            force: Если True, ротирует всегда, даже если User-Agent один
        """
        if hasattr(self, 'user_agents_pool') and len(self.user_agents_pool) > 0:
            if len(self.user_agents_pool) > 1:
                # Выбираем новый User-Agent (не тот же самый)
                available_ua = [ua for ua in self.user_agents_pool if ua != self.current_user_agent]
                if available_ua:
                    new_ua = random.choice(available_ua)
                else:
                    new_ua = random.choice(self.user_agents_pool)
            else:
                # Если только один User-Agent, используем его
                new_ua = self.user_agents_pool[0]
            
            if new_ua != self.current_user_agent or force:
                self.current_user_agent = new_ua
                # Сохраняем для использования в Selenium
                logger.debug(f"User-Agent ротирован: {new_ua[:60]}...")
    
    def _human_delay(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None):
        """
        Имитация человеческой задержки между запросами.
        Увеличено для избежания rate limiting от Instagram.
        
        Args:
            min_seconds: Минимальная задержка (если None - используется self.min_delay)
            max_seconds: Максимальная задержка (если None - используется self.max_delay)
        """
        min_delay = min_seconds if min_seconds is not None else self.min_delay
        max_delay = max_seconds if max_seconds is not None else self.max_delay
        # Добавляем небольшую случайную вариацию для реалистичности
        delay = random.uniform(min_delay, max_delay)
        # Иногда добавляем дополнительную паузу (имитация чтения/просмотра)
        if random.random() < 0.2:  # 20% шанс
            delay += random.uniform(3.0, 8.0)
        
        # Ротируем User-Agent во время задержки (более агрессивная ротация)
        if random.random() < 0.7:  # 70% шанс - более частая ротация
            self._rotate_user_agent()
        
        time.sleep(delay)
        logger.debug(f"Задержка {delay:.2f} сек (имитация человека)")
    
    def collect_videos(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Собрать видео из Instagram источника.
        
        Args:
            limit: Максимальное количество видео
            
        Returns:
            Список информации о видео
        """
        videos = []
        overall_start_time = time.time()
        max_overall_time = 300  # Максимум 5 минут на весь сбор
        
        try:
            if self.source_type == "profile":
                videos = self._collect_from_profile(limit)
            elif self.source_type == "hashtag":
                videos = self._collect_from_hashtag(limit)
            elif self.source_type == "reels":
                videos = self._collect_reels(limit)
            elif self.source_type == "url_list":
                videos = self._collect_from_urls(limit)
            elif self.source_type == "keywords":
                # Сбор по ключевым словам через поиск хэштегов
                videos = self._collect_from_keywords(limit)
            else:
                logger.warning(f"Неподдерживаемый тип источника: {self.source_type}")
            
            # Проверка общего таймаута
            elapsed_time = time.time() - overall_start_time
            if elapsed_time > max_overall_time:
                logger.warning(f"Сбор занял {elapsed_time:.1f} секунд (превышен таймаут)")
            else:
                logger.info(f"Сбор завершён за {elapsed_time:.1f} секунд")
        
        except KeyboardInterrupt:
            logger.warning("Сбор прерван пользователем (Ctrl+C)")
            raise
        except Exception as e:
            logger.error(f"Ошибка сбора видео из Instagram: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return videos
    
    def _collect_from_profile(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """Собрать видео из профиля используя альтернативные методы (HTML парсинг)."""
        videos = []
        
        # Пробуем сначала через Selenium (полностью обходит GraphQL API)
        logger.info(f"Пробую собрать профиль {self.source_value} через Selenium (обходит GraphQL API)...")
        try:
            selenium_videos = self._collect_from_profile_selenium(limit)
            if selenium_videos and len(selenium_videos) > 0:
                logger.info(f"✅ Найдено {len(selenium_videos)} видео через Selenium! Пропускаю instaloader.")
                return selenium_videos
            else:
                logger.info("Selenium не дал результатов, пробую через yt-dlp HTML парсинг...")
        except Exception as e:
            logger.warning(f"Ошибка Selenium: {e}, пробую через yt-dlp...")
        
        # Если Selenium не сработал - пробуем yt-dlp
        try:
            html_videos = self._collect_from_profile_html(limit)
            if html_videos and len(html_videos) > 0:
                logger.info(f"✅ Найдено {len(html_videos)} видео через yt-dlp! Пропускаю instaloader.")
                return html_videos
            else:
                logger.info("yt-dlp не дал результатов, пробую через instaloader...")
        except Exception as e:
            logger.warning(f"Ошибка yt-dlp: {e}, пробую через instaloader...")
        
        # Если HTML парсинг не сработал - пробуем через instaloader
        logger.info(f"HTML парсинг не дал результатов, пробую через instaloader...")
        try:
            # Задержка перед началом (имитация открытия профиля) - сильно увеличено
            self._human_delay(20.0, 30.0)
            # Ротация User-Agent перед началом сбора
            self._rotate_user_agent()
            
            # Пробуем получить профиль с обработкой ошибок
            max_retries = 3
            retry_delay = 60  # 60 секунд между попытками
            profile = None
            
            for attempt in range(max_retries):
                try:
                    profile = Profile.from_username(self.loader.context, self.source_value)
                    break  # Успешно получили профиль
                except Exception as e:
                    error_msg = str(e).lower()
                    if "please wait" in error_msg or "wait a few minutes" in error_msg:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1)  # Экспоненциальная задержка
                            logger.warning(f"Instagram просит подождать. Жду {wait_time} секунд перед повторной попыткой {attempt + 2}/{max_retries}...")
                            time.sleep(wait_time)
                            # Ротируем User-Agent перед повторной попыткой
                            self._rotate_user_agent()
                            continue
                        else:
                            logger.error("Превышено количество попыток. Instagram всё ещё блокирует.")
                            raise
                    else:
                        raise  # Другая ошибка - пробрасываем дальше
            
            if not profile:
                raise Exception("Не удалось получить профиль после всех попыток")
            
            # Получаем Reels с обработкой ошибок
            logger.info(f"Начинаю сбор Reels из профиля {self.source_value}...")
            
            # Пробуем получить Reels с повторными попытками
            reels = None
            max_reels_retries = 3
            for attempt in range(max_reels_retries):
                try:
                    reels = profile.get_reels()
                    break
                except Exception as e:
                    error_msg = str(e).lower()
                    if "please wait" in error_msg or "wait a few minutes" in error_msg:
                        if attempt < max_reels_retries - 1:
                            wait_time = 90 * (attempt + 1)  # 90, 180, 270 секунд
                            logger.warning(f"Ошибка получения Reels. Жду {wait_time} секунд перед повторной попыткой {attempt + 2}/{max_reels_retries}...")
                            time.sleep(wait_time)
                            self._rotate_user_agent()
                            continue
                        else:
                            logger.error("Не удалось получить Reels после всех попыток")
                            return videos
                    else:
                        raise
            
            if not reels:
                logger.error("Не удалось получить Reels")
                return videos
            
            count = 0
            max_iterations = (limit or 10) * 5  # Увеличиваем лимит итераций
            iteration = 0
            start_time = time.time()
            max_time = 600  # Максимум 10 минут на сбор (увеличено)
            
            logger.info(f"Итерация по Reels начата (лимит: {limit}, макс. итераций: {max_iterations})")
            for post in reels:
                # Проверка таймаута
                elapsed = time.time() - start_time
                if elapsed > max_time:
                    logger.warning(f"Превышен таймаут сбора из профиля {self.source_value} ({elapsed:.1f} сек)")
                    break
                
                # Проверка максимального количества итераций
                iteration += 1
                if iteration % 10 == 0:  # Логируем каждые 10 итераций
                    logger.debug(f"Обработано итераций: {iteration}, найдено видео: {count}, время: {elapsed:.1f} сек")
                
                if iteration > max_iterations:
                    logger.warning(f"Достигнуто максимальное количество итераций для профиля {self.source_value} ({iteration})")
                    break
                
                if limit and count >= limit:
                    break
                
                # Задержка между постами (имитация просмотра)
                if count > 0:
                    self._human_delay(*self.post_delay)
                    # Ротация User-Agent между каждым постом для максимальной защиты
                    self._rotate_user_agent()
                
                try:
                    if post.is_video:
                        # Дополнительная задержка перед обработкой видео
                        self._human_delay(5.0, 10.0)
                        video_info = self._extract_video_info(post)
                        if video_info:
                            videos.append(video_info)
                            count += 1
                            logger.info(f"✅ Найдено видео {count}/{limit if limit else '∞'}: @{video_info.get('source_author', 'unknown')}")
                            # Ротация User-Agent после каждого найденного видео
                            self._rotate_user_agent()
                except Exception as e:
                    error_msg = str(e).lower()
                    if "please wait" in error_msg or "wait a few minutes" in error_msg:
                        logger.warning(f"Instagram просит подождать при обработке поста. Жду 120 секунд...")
                        time.sleep(120)
                        self._rotate_user_agent()
                        continue
                    else:
                        logger.debug(f"Ошибка обработки поста: {e}")
                        continue  # Пропускаем проблемный пост
            
            logger.info(f"Собрано {len(videos)} Reels из профиля {self.source_value}")
        
        except KeyboardInterrupt:
            logger.warning("Сбор прерван пользователем")
            raise
        except Exception as e:
            logger.error(f"Ошибка сбора из профиля {self.source_value}: {e}")
        
        return videos
    
    def _collect_reels(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """Собрать Reels из профиля БЕЗ instaloader."""
        return self._collect_from_profile(limit)
    
    def _collect_from_hashtag(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """Собрать видео по хэштегу через Selenium (БЕЗ instaloader)."""
        videos = []
        logger.warning("Сбор по хэштегам через Selenium пока не реализован. Используйте профили.")
        # TODO: Реализовать сбор по хэштегам через Selenium
        return videos
    
    def _collect_from_urls(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """Собрать видео из списка URL через yt-dlp (БЕЗ instaloader)."""
        import json
        videos = []
        
        try:
            url_list = json.loads(self.source_value) if isinstance(self.source_value, str) else self.source_value
            if not isinstance(url_list, list):
                url_list = [url_list]
            
            count = 0
            for url in url_list:
                if limit and count >= limit:
                    break
                
                try:
                    # Извлекаем shortcode из URL
                    shortcode = self._extract_shortcode_from_url(url)
                    if not shortcode:
                        continue
                    
                    # Получаем информацию через yt-dlp
                    import yt_dlp
                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': False,
                        'skip_download': True,
                    }
                    
                    if hasattr(self, 'proxy_url') and self.proxy_url:
                        ydl_opts['proxy'] = self.proxy_url
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if info and info.get('duration'):  # Есть длительность = видео
                            video_info = {
                                "source_url": url,
                                "source_post_id": shortcode,
                                "source_author": info.get('uploader', 'unknown'),
                                "title": info.get('title', ''),
                                "description": info.get('description', ''),
                                "tags": [],
                                "duration": info.get('duration', 0),
                                "video_url": url,
                                "thumbnail_url": info.get('thumbnail'),
                                "metadata": {
                                    "likes": info.get('like_count', 0),
                                    "comments": info.get('comment_count', 0),
                                    "view_count": info.get('view_count', 0),
                                }
                            }
                            videos.append(video_info)
                            count += 1
                            logger.info(f"✅ Найдено видео из URL: {url}")
                except Exception as e:
                    logger.warning(f"Ошибка обработки URL {url}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Ошибка сбора из списка URL: {e}")
        
        return videos
    
    def _collect_from_keywords(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """Собрать видео по ключевым словам через Selenium (БЕЗ instaloader)."""
        videos = []
        logger.warning("Сбор по ключевым словам через Selenium пока не реализован. Используйте профили или URL.")
        # TODO: Реализовать сбор по ключевым словам через Selenium
        return videos
    
    def _collect_from_profile_selenium(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """
        Собрать видео из профиля через Selenium (обходит GraphQL API полностью).
        Парсит HTML страницу напрямую.
        """
        videos = []
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            from bs4 import BeautifulSoup
            import json
            
            profile_url = f"https://www.instagram.com/{self.source_value}/"
            logger.info(f"Открываю профиль через Selenium: {profile_url}")
            
            # Настройка Chrome с ротацией User-Agent
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")  # Безголовый режим
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Используем случайный User-Agent
            if hasattr(self, 'user_agents_pool'):
                user_agent = random.choice(self.user_agents_pool)
            else:
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            chrome_options.add_argument(f"--user-agent={user_agent}")
            
            # Если есть прокси - используем его
            if hasattr(self, 'proxy_url') and self.proxy_url:
                chrome_options.add_argument(f"--proxy-server={self.proxy_url}")
                logger.debug(f"Использую прокси для Selenium: {self.proxy_url}")
            else:
                # Отключаем прокси для Selenium (используем системный VPN)
                chrome_options.add_argument("--no-proxy-server")
            
            # Создаём драйвер с таймаутами
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(30)  # Таймаут загрузки страницы
            driver.implicitly_wait(5)  # Неявное ожидание элементов
            
            start_time = time.time()
            max_time = 60  # Максимум 60 секунд на всю операцию
            
            try:
                logger.info("Открываю страницу профиля...")
                # Открываем профиль с таймаутом
                driver.get(profile_url)
                
                # Проверка таймаута
                if time.time() - start_time > max_time:
                    logger.warning("Превышен таймаут открытия страницы")
                    return []
                
                logger.info("Жду загрузки контента...")
                time.sleep(3)  # Ждём загрузки (уменьшено)
                
                # Проверка таймаута
                if time.time() - start_time > max_time:
                    logger.warning("Превышен таймаут после загрузки")
                    return []
                
                # Прокручиваем страницу для загрузки постов (с таймаутом)
                logger.info("Прокручиваю страницу для загрузки постов...")
                scroll_pause_time = 1  # Уменьшено
                last_height = driver.execute_script("return document.body.scrollHeight")
                scrolls = 0
                max_scrolls = 2  # Максимум 2 прокрутки (уменьшено)
                
                while scrolls < max_scrolls:
                    # Проверка таймаута
                    if time.time() - start_time > max_time:
                        logger.warning("Превышен таймаут при прокрутке")
                        break
                    
                    # Прокручиваем вниз
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(scroll_pause_time)
                    
                    # Проверяем новую высоту
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                    scrolls += 1
                    logger.debug(f"Прокрутка {scrolls}/{max_scrolls}")
                
                # Проверка таймаута перед парсингом
                if time.time() - start_time > max_time:
                    logger.warning("Превышен таймаут перед парсингом HTML")
                    return []
                
                # Парсим HTML
                logger.info("Парсю HTML страницы...")
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем ссылки на посты
                post_links = []
                for link in soup.find_all('a', href=True):
                    # Проверка таймаута
                    if time.time() - start_time > max_time:
                        break
                    
                    href = link.get('href', '')
                    if '/p/' in href or '/reel/' in href or '/reels/' in href:
                        full_url = f"https://www.instagram.com{href}" if href.startswith('/') else href
                        if full_url not in post_links:
                            post_links.append(full_url)
                            if limit and len(post_links) >= (limit or 10) * 2:  # Берём больше для фильтрации
                                break
                
                logger.info(f"Найдено {len(post_links)} ссылок на посты через Selenium")
                
                # Обрабатываем каждую ссылку (быстро, без проверки через yt-dlp)
                for i, post_url in enumerate(post_links[:limit or 10]):
                    # Проверка таймаута
                    if time.time() - start_time > max_time:
                        logger.warning(f"Превышен таймаут при обработке ссылок (обработано {i}/{len(post_links)})")
                        break
                    
                    if limit and len(videos) >= limit:
                        break
                    
                    try:
                        # Извлекаем shortcode
                        shortcode = self._extract_shortcode_from_url(post_url)
                        if not shortcode:
                            continue
                        
                        # Добавляем как видео (yt-dlp проверит при скачивании)
                        video_info = {
                            "source_url": post_url,
                            "source_post_id": shortcode,
                            "source_author": self.source_value,
                            "title": "",
                            "description": "",
                            "tags": [],
                            "duration": 0,
                            "video_url": post_url,
                            "thumbnail_url": None,
                            "metadata": {}
                        }
                        videos.append(video_info)
                        logger.info(f"✅ Найдена ссылка {len(videos)}/{limit or 10}: {post_url}")
                    
                    except Exception as e:
                        logger.debug(f"Ошибка обработки поста {post_url}: {e}")
                        continue
                
                logger.info(f"✅ Всего найдено {len(videos)} видео через Selenium")
                return videos
                
            finally:
                driver.quit()
            
        except ImportError as e:
            logger.warning(f"Selenium не установлен: {e}. Установите: pip install selenium beautifulsoup4 webdriver-manager")
            return []
        except Exception as e:
            logger.error(f"Ошибка сбора через Selenium: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def _collect_from_profile_html(self, limit: Optional[int]) -> List[Dict[str, Any]]:
        """
        Собрать видео из профиля через парсинг HTML (обходит GraphQL API).
        Использует yt-dlp для получения информации о постах.
        """
        videos = []
        try:
            import yt_dlp
            import signal
            
            profile_url = f"https://www.instagram.com/{self.source_value}/"
            logger.info(f"Парсю профиль через HTML: {profile_url}")
            
            # Используем yt-dlp для получения информации о постах профиля
            ydl_opts = {
                'quiet': False,  # Показываем прогресс
                'no_warnings': False,
                'extract_flat': True,  # Только метаданные, не скачиваем
                'playlistend': limit or 20,  # Ограничиваем количество (меньше для скорости)
                'socket_timeout': 30,  # Таймаут подключения
                'retries': 2,  # Меньше попыток
            }
            
            # Если есть прокси - используем его
            if hasattr(self, 'proxy_url') and self.proxy_url:
                ydl_opts['proxy'] = self.proxy_url
                logger.debug(f"Использую прокси для yt-dlp: {self.proxy_url}")
            
            # Таймаут для всей операции (60 секунд)
            start_time = time.time()
            max_time = 60
            
            # Пробуем получить список постов через yt-dlp с таймаутом
            try:
                import threading
                
                info_result = [None]
                error_result = [None]
                
                def extract_with_timeout():
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            logger.info("Запускаю yt-dlp для получения списка постов...")
                            info_result[0] = ydl.extract_info(profile_url, download=False)
                    except Exception as e:
                        error_result[0] = e
                
                # Запускаем в отдельном потоке с таймаутом
                thread = threading.Thread(target=extract_with_timeout, daemon=True)
                thread.start()
                thread.join(timeout=60)  # Максимум 60 секунд
                
                if thread.is_alive():
                    logger.warning("yt-dlp завис, прерываю...")
                    return []  # yt-dlp завис, возвращаем пустой список
                
                if error_result[0]:
                    raise error_result[0]
                
                info = info_result[0]
                
                if not info:
                    logger.warning("yt-dlp не вернул данные")
                    return []
                
                # Проверка таймаута
                if time.time() - start_time > max_time:
                    logger.warning("Превышен таймаут получения списка постов")
                    return []
                
                if info and 'entries' in info:
                    entries = list(info.get('entries', []))[:limit or 20]
                    logger.info(f"Найдено {len(entries)} постов через yt-dlp")
                    
                    for i, entry in enumerate(entries):
                        # Проверка таймаута
                        if time.time() - start_time > max_time:
                            logger.warning(f"Превышен таймаут при обработке постов (обработано {i}/{len(entries)})")
                            break
                        
                        if entry and entry.get('url'):
                            # Извлекаем shortcode из URL
                            shortcode = self._extract_shortcode_from_url(entry['url'])
                            if shortcode:
                                # Проверяем что это видео (не фото)
                                if entry.get('duration') or 'reel' in entry.get('url', '').lower() or 'video' in entry.get('extractor', '').lower():
                                    video_info = {
                                        "source_url": entry['url'],
                                        "source_post_id": shortcode,
                                        "source_author": self.source_value,
                                        "title": entry.get('title', ''),
                                        "description": entry.get('description', ''),
                                        "tags": [],
                                        "duration": entry.get('duration', 0),
                                        "video_url": entry['url'],  # yt-dlp скачает сам
                                        "thumbnail_url": entry.get('thumbnail'),
                                        "metadata": {
                                            "likes": entry.get('like_count', 0),
                                            "comments": entry.get('comment_count', 0),
                                            "view_count": entry.get('view_count', 0),
                                        }
                                    }
                                    videos.append(video_info)
                                    logger.info(f"✅ Найдено видео {len(videos)}/{limit or 20}: {entry['url']}")
                                    
                                    if limit and len(videos) >= limit:
                                        break
                else:
                    logger.warning("yt-dlp не вернул список постов (возможно профиль приватный или недоступен)")
                    return []
            except Exception as e:
                error_msg = str(e).lower()
                if "timeout" in error_msg or "timed out" in error_msg:
                    logger.warning(f"Таймаут при получении постов через yt-dlp: {e}")
                else:
                    logger.warning(f"yt-dlp не смог получить список постов: {e}")
                return []
            
            logger.info(f"✅ Всего найдено {len(videos)} видео через HTML парсинг")
            return videos
            
        except ImportError:
            logger.debug("yt-dlp не установлен для HTML парсинга")
            return []
        except Exception as e:
            logger.debug(f"Ошибка HTML парсинга профиля: {e}")
            return []
    
    def _extract_shortcode_from_url(self, url: str) -> Optional[str]:
        """Извлечь shortcode из URL Instagram."""
        import re
        match = re.search(r'/(?:p|reel|reels)/([^/?#]+)/?', url)
        return match.group(1) if match else None
    
    def _extract_video_info(self, post: Any) -> Optional[Dict[str, Any]]:
        """
        Извлечь информацию о видео из поста.
        Теперь работает с данными от yt-dlp/Selenium, а не instaloader Post.
        """
        # Этот метод больше не используется для instaloader Post
        # Информация извлекается напрямую в методах сбора
        return None
    
    def download_video(self, video_url: str, output_path: str) -> bool:
        """
        Скачать видео по URL используя yt-dlp (обходит GraphQL API и блокировки).
        
        Args:
            video_url: URL видео Instagram (например https://www.instagram.com/p/ABC123/)
            output_path: Путь для сохранения
            
        Returns:
            True если успешно
        """
        try:
            import yt_dlp
            from pathlib import Path
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Настройки yt-dlp для Instagram
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': str(output_file.with_suffix('')) + '.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'noplaylist': True,
            }
            
            # Если есть прокси - используем его
            if hasattr(self, 'proxy_url') and self.proxy_url:
                ydl_opts['proxy'] = self.proxy_url
                logger.debug(f"Использую прокси для yt-dlp: {self.proxy_url}")
            
            # Пробуем использовать cookies из браузера для авторизации
            try:
                import browser_cookie3
                # Пробуем получить cookies из Chrome
                cookies = browser_cookie3.chrome(domain_name='instagram.com')
                if cookies:
                    # Сохраняем cookies во временный файл для yt-dlp
                    import tempfile
                    cookies_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
                    for cookie in cookies:
                        cookies_file.write(f"{cookie.domain}\tTRUE\t{cookie.path}\tFALSE\t{cookie.expires or 0}\t{cookie.name}\t{cookie.value}\n")
                    cookies_file.close()
                    ydl_opts['cookiefile'] = cookies_file.name
                    logger.debug("Использую cookies из браузера для yt-dlp")
            except Exception as e:
                logger.debug(f"Не удалось загрузить cookies из браузера: {e}")
            
            # Скачиваем через yt-dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            
            # Проверяем что файл создан
            # yt-dlp может изменить расширение, ищем любой видео файл
            possible_files = list(output_file.parent.glob(f"{output_file.stem}.*"))
            video_files = [f for f in possible_files if f.suffix in ['.mp4', '.webm', '.mkv', '.m4a']]
            
            if video_files:
                # Переименовываем в нужный формат если нужно
                downloaded_file = video_files[0]
                if downloaded_file != output_file:
                    downloaded_file.rename(output_file)
                logger.info(f"✅ Видео скачано через yt-dlp: {output_path}")
                return True
            else:
                logger.error(f"Файл не найден после скачивания: {output_path}")
                return False
        
        except ImportError:
            logger.error("yt-dlp не установлен. Установите: pip install yt-dlp")
            # Fallback на старый метод
            return self._download_video_fallback(video_url, output_path)
        except Exception as e:
            logger.error(f"Ошибка скачивания видео через yt-dlp {video_url}: {e}")
            # Fallback на старый метод
            return self._download_video_fallback(video_url, output_path)
    
    def _download_video_fallback(self, video_url: str, output_path: str) -> bool:
        """Fallback метод скачивания через requests."""
        import requests
        from pathlib import Path
        
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Скачиваем видео
            response = requests.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Видео скачано (fallback метод): {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"Ошибка скачивания видео (fallback) {video_url}: {e}")
            return False
