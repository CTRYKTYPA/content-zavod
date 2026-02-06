"""
Альтернативные методы скачивания видео с Instagram БЕЗ instaloader.
Использует user agents из файла useragents.txt.
"""
import requests
import json
import re
import random
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from loguru import logger


def load_user_agents(file_path: str = "useragents.txt") -> List[str]:
    """Загрузить user agents из файла."""
    user_agents = []
    try:
        full_path = Path(file_path)
        if not full_path.is_absolute():
            # Ищем относительно корня проекта
            full_path = Path(__file__).parent.parent.parent / file_path
        
        if full_path.exists():
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and len(line) > 30:
                        # Фильтруем только десктопные браузеры
                        if ('Chrome/' in line or 'Firefox/' in line) and 'Mobile' not in line and 'Android' not in line:
                            if 'Windows' in line or 'Macintosh' in line or 'Linux' in line or 'X11' in line:
                                user_agents.append(line)
        else:
            logger.warning(f"Файл user agents не найден: {full_path}")
    except Exception as e:
        logger.warning(f"Ошибка загрузки user agents: {e}")
    
    # Дефолтные user agents если файл не найден
    if not user_agents:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        ]
    
    logger.debug(f"Загружено {len(user_agents)} user agents")
    return user_agents


def extract_shortcode(url: str) -> Optional[str]:
    """Извлечь shortcode из URL Instagram."""
    patterns = [
        r'/p/([^/?]+)',
        r'/reel/([^/?]+)',
        r'/reels/([^/?]+)',
        r'/tv/([^/?]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_csrf_token(session: requests.Session, user_agent: str) -> Optional[str]:
    """Получить CSRF токен из главной страницы Instagram."""
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.instagram.com/',
    }
    
    try:
        response = session.get('https://www.instagram.com/', headers=headers, timeout=10)
        # Ищем csrf токен в cookies
        csrf_token = response.cookies.get('csrftoken')
        if not csrf_token:
            # Пробуем извлечь из HTML
            match = re.search(r'"csrf_token":"([^"]+)"', response.text)
            if match:
                csrf_token = match.group(1)
        return csrf_token
    except Exception as e:
        logger.debug(f"Ошибка получения CSRF токена: {e}")
        return None


def download_video_file(session: requests.Session, video_url: str, output_path: str) -> bool:
    """Скачать видео файл по прямой ссылке."""
    try:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        response = session.get(video_url, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(output_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        if progress % 10 == 0:  # Логируем каждые 10%
                            logger.debug(f"Скачивание: {progress:.1f}%")
        
        logger.info(f"✅ Видео скачано: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка скачивания файла: {e}")
        return False


def extract_video_url_from_data(data: dict) -> Optional[str]:
    """Извлечь URL видео из структуры данных Instagram."""
    try:
        # Различные пути в структуре данных
        paths = [
            ['entry_data', 'PostPage', 0, 'graphql', 'shortcode_media', 'video_url'],
            ['entry_data', 'PostPage', 0, 'graphql', 'shortcode_media', 'video_versions', 0, 'url'],
            ['graphql', 'shortcode_media', 'video_url'],
            ['graphql', 'shortcode_media', 'video_versions', 0, 'url'],
        ]
        
        for path in paths:
            value = data
            try:
                for key in path:
                    if isinstance(key, int):
                        value = value[key]
                    else:
                        value = value[key]
                if value and isinstance(value, str) and value.startswith('http'):
                    return value
            except (KeyError, IndexError, TypeError):
                continue
        
        return None
    except Exception as e:
        logger.debug(f"Ошибка извлечения URL: {e}")
        return None


def download_video_graphql(url: str, output_path: str, user_agents_file: str = "useragents.txt") -> bool:
    """
    Скачать видео через GraphQL API.
    
    Args:
        url: URL поста Instagram
        output_path: Путь для сохранения видео
        user_agents_file: Путь к файлу с user agents
    
    Returns:
        True если успешно
    """
    user_agents = load_user_agents(user_agents_file)
    user_agent = random.choice(user_agents)
    
    session = requests.Session()
    
    # Получаем CSRF токен
    csrf_token = get_csrf_token(session, user_agent)
    if not csrf_token:
        logger.warning("Не удалось получить CSRF токен")
        return False
    
    # Извлекаем shortcode
    shortcode = extract_shortcode(url)
    if not shortcode:
        logger.warning(f"Не удалось извлечь shortcode из URL: {url}")
        return False
    
    # GraphQL запрос
    graphql_url = "https://www.instagram.com/graphql/query/"
    
    # ВАЖНО: doc_id меняется каждые 2-4 недели!
    # Текущий doc_id можно найти в DevTools браузера при открытии поста
    doc_ids = [
        "7950326061742207",  # Для получения информации о посте
        "24368985919464652",  # Альтернативный
        "17888483320059182",  # Еще один вариант
    ]
    
    headers = {
        'User-Agent': user_agent,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': csrf_token,
        'X-IG-App-ID': '936619743392459',  # Веб-версия Instagram
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': 'https://www.instagram.com',
        'Referer': f'https://www.instagram.com/p/{shortcode}/',
    }
    
    # Пробуем разные doc_id
    for doc_id in doc_ids:
        data = {
            'variables': json.dumps({"shortcode": shortcode}),
            'doc_id': doc_id
        }
        
        try:
            response = session.post(graphql_url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                
                # Извлекаем URL видео из ответа
                video_url = None
                try:
                    data = result.get('data', {})
                    shortcode_media = data.get('shortcode_media', {})
                    
                    if shortcode_media.get('is_video'):
                        video_url = shortcode_media.get('video_url')
                        if not video_url:
                            # Пробуем найти в других местах
                            video_versions = shortcode_media.get('video_versions', [])
                            if video_versions:
                                video_url = video_versions[0].get('url')
                except Exception as e:
                    logger.debug(f"Ошибка парсинга ответа: {e}")
                    continue
                
                if video_url:
                    return download_video_file(session, video_url, output_path)
            else:
                logger.debug(f"Ошибка GraphQL запроса: {response.status_code}")
                continue
                
        except Exception as e:
            logger.debug(f"Ошибка при запросе с doc_id {doc_id}: {e}")
            continue
    
    return False


def download_video_direct(url: str, output_path: str, user_agents_file: str = "useragents.txt") -> bool:
    """
    Скачать видео через прямые HTTP запросы с парсингом HTML.
    
    Args:
        url: URL поста Instagram
        output_path: Путь для сохранения
        user_agents_file: Путь к файлу с user agents
    
    Returns:
        True если успешно
    """
    user_agents = load_user_agents(user_agents_file)
    user_agent = random.choice(user_agents)
    
    session = requests.Session()
    
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
    }
    
    try:
        # Получаем HTML страницу
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        html = response.text
        
        # Ищем JSON данные в HTML
        # Паттерн 1: window._sharedData
        match = re.search(r'window\._sharedData\s*=\s*({.+?});', html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                video_url = extract_video_url_from_data(data)
                if video_url:
                    return download_video_file(session, video_url, output_path)
            except Exception as e:
                logger.debug(f"Ошибка парсинга _sharedData: {e}")
        
        # Паттерн 2: JSON-LD
        match = re.search(r'<script type="application/ld\+json">(.+?)</script>', html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                video_url = data.get('contentUrl') or data.get('video', {}).get('contentUrl')
                if video_url:
                    return download_video_file(session, video_url, output_path)
            except Exception as e:
                logger.debug(f"Ошибка парсинга JSON-LD: {e}")
        
        # Паттерн 3: Прямой поиск video_url в HTML
        patterns = [
            r'"video_url":"([^"]+)"',
            r'"videoUrl":"([^"]+)"',
            r'<meta property="og:video" content="([^"]+)"',
            r'<meta property="og:video:secure_url" content="([^"]+)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for match_url in matches:
                if 'video' in match_url.lower() or 'mp4' in match_url.lower():
                    # Декодируем URL если нужно
                    video_url = match_url.replace('\\u0026', '&').replace('\\/', '/')
                    if download_video_file(session, video_url, output_path):
                        return True
        
        logger.warning("Не удалось найти URL видео в HTML")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка прямого скачивания: {e}")
        return False


def download_video_ytdlp(url: str, output_path: str, user_agents_file: str = "useragents.txt", 
                         proxy: Optional[str] = None) -> bool:
    """
    Скачать видео через yt-dlp с ротацией user agents.
    
    Args:
        url: URL поста Instagram
        output_path: Путь для сохранения
        user_agents_file: Путь к файлу с user agents
        proxy: Прокси (опционально)
    
    Returns:
        True если успешно
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp не установлен. Установите: pip install yt-dlp")
        return False
    
    user_agents = load_user_agents(user_agents_file)
    user_agent = random.choice(user_agents)
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Настройки yt-dlp
    # Используем best вместо bestvideo+bestaudio чтобы не требовался ffmpeg
    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Берем лучшее качество без объединения
        'outtmpl': str(output_file.with_suffix('')) + '.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'noplaylist': True,
        'user_agent': user_agent,
        'referer': 'https://www.instagram.com/',
        'headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'X-IG-App-ID': '936619743392459',
        },
        'socket_timeout': 30,
        'retries': 3,
        'merge_output_format': None,  # Отключаем объединение
    }
    
    # Добавляем прокси если есть
    if proxy:
        ydl_opts['proxy'] = proxy
    
    # Пробуем использовать cookies из браузера
    try:
        import browser_cookie3
        cookies = browser_cookie3.chrome(domain_name='instagram.com')
        if cookies:
            import tempfile
            cookies_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
            for cookie in cookies:
                cookies_file.write(
                    f"{cookie.domain}\tTRUE\t{cookie.path}\tFALSE\t"
                    f"{cookie.expires or 0}\t{cookie.name}\t{cookie.value}\n"
                )
            cookies_file.close()
            ydl_opts['cookiefile'] = cookies_file.name
            logger.debug("Использую cookies из браузера для yt-dlp")
    except Exception:
        pass
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Проверяем что файл создан
        possible_files = list(output_file.parent.glob(f"{output_file.stem}.*"))
        video_files = [f for f in possible_files if f.suffix in ['.mp4', '.webm', '.mkv', '.m4a']]
        
        if video_files:
            downloaded_file = video_files[0]
            if downloaded_file != output_file:
                downloaded_file.rename(output_file)
            logger.info(f"✅ Видео скачано через yt-dlp: {output_path}")
            return True
        else:
            logger.error(f"Файл не найден после скачивания: {output_path}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка скачивания через yt-dlp: {e}")
        return False


def download_video_api_v1(url: str, output_path: str, user_agents_file: str = "useragents.txt") -> bool:
    """
    Скачать видео через Instagram API v1.
    
    Args:
        url: URL поста Instagram
        output_path: Путь для сохранения
        user_agents_file: Путь к файлу с user agents
    
    Returns:
        True если успешно
    """
    user_agents = load_user_agents(user_agents_file)
    user_agent = random.choice(user_agents)
    
    shortcode = extract_shortcode(url)
    if not shortcode:
        return False
    
    session = requests.Session()
    
    # Получаем информацию о посте через API v1
    api_url = f"https://www.instagram.com/api/v1/media/{shortcode}/info/"
    
    headers = {
        'User-Agent': user_agent,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'X-IG-App-ID': '936619743392459',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'https://www.instagram.com/p/{shortcode}/',
        'Origin': 'https://www.instagram.com',
    }
    
    try:
        response = session.get(api_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            # Извлекаем URL видео
            video_url = None
            try:
                items = data.get('items', [])
                if items:
                    item = items[0]
                    if item.get('media_type') == 2:  # 2 = видео
                        video_versions = item.get('video_versions', [])
                        if video_versions:
                            # Берем лучшее качество
                            video_url = video_versions[0].get('url')
            except Exception as e:
                logger.debug(f"Ошибка парсинга API ответа: {e}")
                return False
            
            if video_url:
                return download_video_file(session, video_url, output_path)
            else:
                logger.warning("URL видео не найден в ответе API")
                return False
        else:
            logger.debug(f"Ошибка API запроса: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка запроса к API v1: {e}")
        return False


def download_video_html_parsing(url: str, output_path: str, user_agents_file: str = "useragents.txt") -> bool:
    """
    Скачать видео через парсинг HTML страницы.
    
    Args:
        url: URL поста Instagram
        output_path: Путь для сохранения
        user_agents_file: Путь к файлу с user agents
    
    Returns:
        True если успешно
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("BeautifulSoup не установлен. Установите: pip install beautifulsoup4")
        return False
    
    user_agents = load_user_agents(user_agents_file)
    user_agent = random.choice(user_agents)
    
    session = requests.Session()
    
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем meta теги с видео
        video_url = None
        
        # og:video
        og_video = soup.find('meta', property='og:video')
        if og_video:
            video_url = og_video.get('content')
        
        # og:video:secure_url
        if not video_url:
            og_video_secure = soup.find('meta', property='og:video:secure_url')
            if og_video_secure:
                video_url = og_video_secure.get('content')
        
        # Ищем в script тегах
        if not video_url:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        video_url = data.get('contentUrl') or data.get('video', {}).get('contentUrl')
                        if video_url:
                            break
                except:
                    continue
        
        # Ищем в window._sharedData
        if not video_url:
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'window._sharedData' in script.string:
                    match = re.search(r'window\._sharedData\s*=\s*({.+?});', script.string, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            video_url = extract_video_url_from_data(data)
                            if video_url:
                                break
                        except:
                            continue
        
        if video_url:
            return download_video_file(session, video_url, output_path)
        else:
            logger.warning("Не удалось найти URL видео в HTML")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка HTML парсинга: {e}")
        return False


def download_video_selenium(url: str, output_path: str, user_agents_file: str = "useragents.txt",
                           proxy: Optional[str] = None) -> bool:
    """
    Скачать видео через Selenium (получаем прямую ссылку, затем скачиваем через requests).
    
    Args:
        url: URL поста Instagram
        output_path: Путь для сохранения
        user_agents_file: Путь к файлу с user agents
        proxy: Прокси (опционально)
    
    Returns:
        True если успешно
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        logger.error("Selenium не установлен. Установите: pip install selenium webdriver-manager")
        return False
    
    user_agents = load_user_agents(user_agents_file)
    user_agent = random.choice(user_agents)
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument(f"--user-agent={user_agent}")
    
    if proxy:
        chrome_options.add_argument(f"--proxy-server={proxy}")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        driver.get(url)
        time.sleep(5)  # Ждем загрузки
        
        # Ищем видео элемент
        video_elements = driver.find_elements("tag name", "video")
        
        if video_elements:
            video_url = video_elements[0].get_attribute("src")
            if video_url:
                # Скачиваем через requests
                session = requests.Session()
                session.headers.update({'User-Agent': user_agent})
                
                return download_video_file(session, video_url, output_path)
        
        # Альтернативный способ - ищем в JavaScript переменных
        page_source = driver.page_source
        
        # Ищем video_url в HTML
        patterns = [
            r'"video_url":"([^"]+)"',
            r'"videoUrl":"([^"]+)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, page_source)
            for match_url in matches:
                video_url = match_url.replace('\\u0026', '&').replace('\\/', '/')
                if video_url.startswith('http'):
                    session = requests.Session()
                    session.headers.update({'User-Agent': user_agent})
                    return download_video_file(session, video_url, output_path)
        
        logger.warning("Не удалось найти URL видео через Selenium")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка Selenium: {e}")
        return False
    finally:
        driver.quit()


def download_video_combined(url: str, output_path: str, user_agents_file: str = "useragents.txt",
                           proxy: Optional[str] = None) -> bool:
    """
    Комбинированный метод - пробует все способы по очереди.
    
    Порядок попыток:
    1. yt-dlp (самый надежный)
    2. GraphQL API
    3. Прямые HTTP запросы
    4. HTML парсинг
    5. Instagram API v1
    6. Selenium (самый медленный)
    
    Args:
        url: URL поста Instagram
        output_path: Путь для сохранения
        user_agents_file: Путь к файлу с user agents
        proxy: Прокси (опционально)
    
    Returns:
        True если успешно
    """
    methods = [
        ("yt-dlp", lambda: download_video_ytdlp(url, output_path, user_agents_file, proxy)),
        ("GraphQL API", lambda: download_video_graphql(url, output_path, user_agents_file)),
        ("Прямые HTTP", lambda: download_video_direct(url, output_path, user_agents_file)),
        ("HTML парсинг", lambda: download_video_html_parsing(url, output_path, user_agents_file)),
        ("API v1", lambda: download_video_api_v1(url, output_path, user_agents_file)),
        ("Selenium", lambda: download_video_selenium(url, output_path, user_agents_file, proxy)),
    ]
    
    for method_name, method_func in methods:
        logger.info(f"Пробую метод: {method_name}...")
        try:
            if method_func():
                logger.info(f"✅ Успешно через {method_name}")
                return True
        except Exception as e:
            logger.debug(f"Ошибка метода {method_name}: {e}")
            continue
    
    logger.error("❌ Все методы не сработали")
    return False
