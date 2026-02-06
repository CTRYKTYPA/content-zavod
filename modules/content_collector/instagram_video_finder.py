"""
Автоматический поиск видео в Instagram и сохранение ссылок.
Использует существующий модуль instagram_downloader для скачивания.
"""
import time
import random
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger
from datetime import datetime

from .instagram_downloader import (
    download_video_combined,
    download_video_ytdlp,
    extract_shortcode,
    load_user_agents,
)

# Импортируем настройки
try:
    from config import settings
except ImportError:
    # Если config не доступен, создаем пустые настройки
    class Settings:
        INSTAGRAM_USERNAME = None
        INSTAGRAM_PASSWORD = None
    settings = Settings()


class InstagramVideoFinder:
    """Класс для автоматического поиска и скачивания видео с Instagram."""
    
    def __init__(self, user_agents_file: str = "useragents.txt"):
        """
        Инициализация поисковика видео.
        
        Args:
            user_agents_file: Путь к файлу с user agents
        """
        self.user_agents = load_user_agents(user_agents_file)
        logger.info(f"Загружено {len(self.user_agents)} user agents")
        
        # Папка для сохранения ссылок
        self.links_dir = Path("instagram_links")
        self.links_dir.mkdir(exist_ok=True)
        
        # Папка для скачанных видео
        self.downloads_dir = Path("test_downloads")
        self.downloads_dir.mkdir(exist_ok=True)
        
        # Данные для авторизации
        self.username = settings.INSTAGRAM_USERNAME
        self.password = settings.INSTAGRAM_PASSWORD
        self.is_authenticated = False
    
    def find_videos_from_profile(self, username: str, limit: int = 10) -> List[str]:
        """
        Найти видео из профиля Instagram через Selenium.
        
        Args:
            username: Имя пользователя (без @)
            limit: Максимальное количество видео
        
        Returns:
            Список URL видео
        """
        logger.info(f"Ищу видео в профиле @{username}...")
        
        video_urls = []
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            from bs4 import BeautifulSoup
            import re
            
            profile_url = f"https://www.instagram.com/{username}/"
            user_agent = random.choice(self.user_agents)
            
            logger.info(f"Открываю профиль через Selenium: {profile_url}")
            
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument(f"--user-agent={user_agent}")
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(30)
            
            try:
                driver.get(profile_url)
                time.sleep(5)  # Ждем загрузки
                
                # Прокручиваем страницу для загрузки постов
                logger.info("Прокручиваю страницу для загрузки постов...")
                scroll_pause_time = 2
                last_height = driver.execute_script("return document.body.scrollHeight")
                scrolls = 0
                max_scrolls = 3
                
                while scrolls < max_scrolls:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(scroll_pause_time)
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                    scrolls += 1
                
                # Парсим HTML
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем ссылки на посты
                post_links = []
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/p/' in href or '/reel/' in href or '/reels/' in href:
                        full_url = f"https://www.instagram.com{href}" if href.startswith('/') else href
                        if full_url not in post_links:
                            post_links.append(full_url)
                            if len(post_links) >= limit * 2:  # Берем больше для фильтрации
                                break
                
                logger.info(f"Найдено {len(post_links)} ссылок на посты")
                
                # Фильтруем - берем только Reels и посты с видео
                for post_url in post_links[:limit]:
                    if '/reel/' in post_url.lower() or '/reels/' in post_url.lower():
                        video_urls.append(post_url)
                        logger.debug(f"Найдено Reel: {post_url}")
                    elif '/p/' in post_url.lower():
                        # Проверяем что это видео (не фото) - добавляем все, yt-dlp проверит при скачивании
                        video_urls.append(post_url)
                        logger.debug(f"Найден пост: {post_url}")
                
                logger.info(f"Найдено {len(video_urls)} видео в профиле @{username}")
                
            finally:
                driver.quit()
            
        except ImportError:
            logger.error("Selenium не установлен. Установите: pip install selenium beautifulsoup4 webdriver-manager")
        except Exception as e:
            logger.error(f"Ошибка поиска видео в профиле @{username}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return video_urls
    
    def _login_to_instagram(self, driver) -> bool:
        """
        Авторизоваться в Instagram через Selenium.
        
        Args:
            driver: WebDriver объект
        
        Returns:
            True если успешно
        """
        if not self.username or not self.password:
            logger.warning("Логин/пароль не указаны в настройках. Продолжаю без авторизации.")
            return False
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            logger.info(f"Авторизуюсь в Instagram как {self.username}...")
            
            driver.get("https://www.instagram.com/accounts/login/")
            time.sleep(5)  # Увеличиваем задержку для загрузки страницы
            
            # Вводим логин
            try:
                logger.info("Ищу поле для ввода логина...")
                username_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.NAME, "username"))
                )
                logger.info("Поле логина найдено, ввожу данные...")
                username_input.clear()
                time.sleep(0.5)
                username_input.send_keys(self.username)
                logger.info(f"Логин введен: {self.username}")
            except Exception as e:
                logger.error(f"Не удалось найти поле логина: {e}")
                logger.debug(f"Текущий URL: {driver.current_url}")
                logger.debug(f"Страница: {driver.page_source[:500]}")
                return False
            
            # Вводим пароль
            try:
                logger.info("Ищу поле для ввода пароля...")
                password_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.NAME, "password"))
                )
                logger.info("Поле пароля найдено, ввожу данные...")
                password_input.clear()
                time.sleep(0.5)
                password_input.send_keys(self.password)
                logger.info("Пароль введен")
            except Exception as e:
                logger.error(f"Не удалось найти поле пароля: {e}")
                return False
            
            # Нажимаем войти
            try:
                logger.info("Ищу кнопку входа...")
                login_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
                )
                logger.info("Кнопка найдена, нажимаю...")
                login_button.click()
                logger.info("Кнопка нажата, жду ответа...")
                time.sleep(8)  # Увеличиваем задержку для обработки входа
            except Exception as e:
                logger.error(f"Не удалось нажать кнопку входа: {e}")
                return False
            
            # Проверяем что мы вошли
            current_url = driver.current_url
            logger.info(f"Текущий URL после входа: {current_url}")
            
            if "instagram.com/accounts/login" not in current_url:
                logger.info("Авторизация успешна!")
                self.is_authenticated = True
                return True
            else:
                logger.warning("Авторизация не удалась или требуется подтверждение")
                # Проверяем есть ли сообщение об ошибке
                try:
                    error_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'error')]")
                    if error_elements:
                        logger.warning(f"Ошибка авторизации: {error_elements[0].text}")
                except:
                    pass
                return False
                
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def find_videos_from_hashtag_fast(self, hashtag: str, limit: int = 10) -> List[str]:
        """
        Быстрый поиск видео БЕЗ браузера через requests.
        
        Args:
            hashtag: Хэштег (без #)
            limit: Максимальное количество видео
        
        Returns:
            Список URL видео
        """
        logger.info(f"Быстрый поиск по хэштегу #{hashtag} БЕЗ браузера...")
        
        video_urls = []
        hashtag_url = f"https://www.instagram.com/explore/tags/{hashtag}/"
        user_agent = random.choice(self.user_agents)
        
        try:
            session = requests.Session()
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.instagram.com/',
            }
            
            response = session.get(hashtag_url, headers=headers, timeout=15)
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Ищем ВСЕ ссылки
                post_links = []
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/p/' in href or '/reel/' in href or '/reels/' in href:
                        full_url = f"https://www.instagram.com{href}" if href.startswith('/') else href
                        if '?' in full_url:
                            full_url = full_url.split('?')[0]
                        if full_url not in post_links:
                            post_links.append(full_url)
                
                video_urls = post_links[:limit * 3]  # Берем больше
                logger.info(f"✅ БЕЗ браузера найдено {len(video_urls)} ссылок!")
            else:
                logger.debug(f"Статус {response.status_code}, нужен браузер")
        except Exception as e:
            logger.debug(f"Быстрый поиск не удался: {e}")
        
        return video_urls
    
    def find_videos_from_hashtag(self, hashtag: str, limit: int = 10) -> List[str]:
        """
        Найти видео по хэштегу через Selenium с авторизацией.
        
        Args:
            hashtag: Хэштег (без #)
            limit: Максимальное количество видео
        
        Returns:
            Список URL видео
        """
        logger.info(f"Ищу видео по хэштегу #{hashtag}...")
        
        video_urls = []
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            from bs4 import BeautifulSoup
            
            hashtag_url = f"https://www.instagram.com/explore/tags/{hashtag}/"
            user_agent = random.choice(self.user_agents)
            
            logger.info(f"Открываю хэштег через Selenium: {hashtag_url}")
            
            chrome_options = Options()
            # Убираем headless для авторизации и лучшего парсинга
            # chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument(f"--user-agent={user_agent}")
            chrome_options.add_argument("--window-size=1920,1080")
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(60)
            driver.implicitly_wait(10)
            
            try:
                # ВСЕГДА авторизуемся ПЕРЕД поиском если есть логин/пароль
                if self.username and self.password:
                    logger.info("="*70)
                    logger.info("ВЫПОЛНЯЮ АВТОРИЗАЦИЮ В INSTAGRAM")
                    logger.info("="*70)
                    login_success = self._login_to_instagram(driver)
                    if login_success:
                        logger.info("✅ Авторизация успешна, продолжаю поиск...")
                        time.sleep(5)  # Ждем после авторизации
                    else:
                        logger.warning("⚠️ Авторизация не удалась, продолжаю без авторизации...")
                else:
                    logger.warning("Логин/пароль не указаны в .env файле!")
                
                logger.info(f"Открываю страницу хэштега: {hashtag_url}")
                driver.get(hashtag_url)
                time.sleep(8)  # Увеличиваем задержку для загрузки контента
                
                # Прокручиваем для загрузки постов (больше прокруток для большего количества постов)
                logger.info("Прокручиваю страницу для загрузки всех постов...")
                scroll_count = 0
                max_scrolls = 10  # Увеличиваем для получения большего количества постов
                last_height = driver.execute_script("return document.body.scrollHeight")
                
                for i in range(max_scrolls):
                    # Прокручиваем вниз
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(4)  # Увеличиваем задержку между прокрутками
                    
                    # Проверяем новую высоту
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        logger.debug(f"Достигнут конец страницы после {i+1} прокруток")
                        break
                    last_height = new_height
                    scroll_count += 1
                    logger.debug(f"Прокрутка {scroll_count}/{max_scrolls}, высота: {new_height}")
                
                logger.info(f"Завершено {scroll_count} прокруток, парсю HTML...")
                time.sleep(3)  # Финальная задержка перед парсингом
                
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем ВСЕ ссылки на посты и рилсы
                post_links = []
                logger.info("Ищу все ссылки на посты и рилсы в HTML...")
                
                # Ищем все ссылки с /p/ и /reel/
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/p/' in href or '/reel/' in href or '/reels/' in href:
                        full_url = f"https://www.instagram.com{href}" if href.startswith('/') else href
                        # Убираем параметры из URL
                        if '?' in full_url:
                            full_url = full_url.split('?')[0]
                        if full_url not in post_links:
                            post_links.append(full_url)
                
                logger.info(f"Найдено {len(post_links)} ссылок на посты/рилсы")
                
                # Берем все найденные (не ограничиваем limit, так как уже отфильтровали)
                video_urls = post_links[:limit * 3] if limit else post_links  # Берем больше для фильтрации
                logger.info(f"Отобрано {len(video_urls)} видео по хэштегу #{hashtag}")
                
            finally:
                driver.quit()
            
        except ImportError:
            logger.error("Selenium не установлен. Установите: pip install selenium beautifulsoup4 webdriver-manager")
        except Exception as e:
            logger.error(f"Ошибка поиска видео по хэштегу #{hashtag}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return video_urls
    
    def save_links(self, video_urls: List[str], filename: str = None) -> Path:
        """
        Сохранить ссылки на видео в файл.
        
        Args:
            video_urls: Список URL видео
            filename: Имя файла (если None - автоматически)
        
        Returns:
            Путь к сохраненному файлу
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"video_links_{timestamp}.txt"
        
        links_file = self.links_dir / filename
        
        with open(links_file, 'w', encoding='utf-8') as f:
            for url in video_urls:
                f.write(f"{url}\n")
        
        logger.info(f"Сохранено {len(video_urls)} ссылок в {links_file}")
        return links_file
    
    def load_links(self, filename: str) -> List[str]:
        """
        Загрузить ссылки из файла.
        
        Args:
            filename: Имя файла
        
        Returns:
            Список URL видео
        """
        links_file = self.links_dir / filename
        
        if not links_file.exists():
            logger.error(f"Файл {links_file} не найден")
            return []
        
        video_urls = []
        with open(links_file, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if url and 'instagram.com' in url:
                    video_urls.append(url)
        
        logger.info(f"Загружено {len(video_urls)} ссылок из {links_file}")
        return video_urls
    
    def download_videos(self, video_urls: List[str], use_combined: bool = True, 
                       delay_between: float = 5.0) -> Dict[str, bool]:
        """
        Скачать видео по списку URL.
        
        Args:
            video_urls: Список URL видео
            use_combined: Использовать комбинированный метод (True) или только yt-dlp (False)
            delay_between: Задержка между скачиваниями (секунды)
        
        Returns:
            Словарь {URL: успешно/неуспешно}
        """
        results = {}
        
        logger.info(f"Начинаю скачивание {len(video_urls)} видео...")
        
        for i, url in enumerate(video_urls, 1):
            logger.info(f"\n[{i}/{len(video_urls)}] Скачиваю: {url}")
            
            # Извлекаем shortcode для имени файла
            shortcode = extract_shortcode(url) or f"video_{i}"
            output_path = self.downloads_dir / f"{shortcode}.mp4"
            
            # Пропускаем если уже скачано
            if output_path.exists():
                logger.info(f"Файл уже существует, пропускаю: {output_path}")
                results[url] = True
                continue
            
            try:
                # Используем протестированный метод
                if use_combined:
                    success = download_video_combined(url, str(output_path))
                else:
                    success = download_video_ytdlp(url, str(output_path))
                
                if success and output_path.exists():
                    file_size = output_path.stat().st_size / 1024 / 1024
                    logger.info(f"[SUCCESS] Видео скачано: {file_size:.2f} MB")
                    results[url] = True
                else:
                    logger.warning(f"[FAIL] Не удалось скачать")
                    results[url] = False
                
            except Exception as e:
                logger.error(f"[ERROR] Ошибка скачивания: {e}")
                results[url] = False
            
            # Задержка между скачиваниями
            if i < len(video_urls):
                delay = delay_between + random.uniform(0, 2)
                logger.debug(f"Задержка {delay:.1f} сек перед следующим видео...")
                time.sleep(delay)
        
        # Статистика
        successful = sum(1 for v in results.values() if v)
        logger.info(f"\n{'='*70}")
        logger.info(f"СКАЧИВАНИЕ ЗАВЕРШЕНО")
        logger.info(f"Успешно: {successful}/{len(video_urls)}")
        logger.info(f"Неудачно: {len(video_urls) - successful}/{len(video_urls)}")
        logger.info(f"{'='*70}")
        
        return results
    
    def find_and_download(self, source: str, source_type: str = "profile", 
                         limit: int = 10, save_links: bool = True) -> Dict[str, Any]:
        """
        Найти видео и сразу скачать их.
        
        Args:
            source: Источник (имя профиля или хэштег)
            source_type: Тип источника ("profile" или "hashtag")
            limit: Максимальное количество видео
            save_links: Сохранять ли ссылки в файл
        
        Returns:
            Словарь с результатами
        """
        logger.info(f"Поиск и скачивание видео из {source_type}: {source}")
        
        # Ищем видео
        if source_type == "profile":
            video_urls = self.find_videos_from_profile(source, limit)
        elif source_type == "hashtag":
            video_urls = self.find_videos_from_hashtag(source, limit)
        else:
            logger.error(f"Неизвестный тип источника: {source_type}")
            return {}
        
        if not video_urls:
            logger.warning("Видео не найдены")
            return {}
        
        # Сохраняем ссылки если нужно
        links_file = None
        if save_links:
            links_file = self.save_links(video_urls)
        
        # Скачиваем видео
        download_results = self.download_videos(video_urls)
        
        return {
            'found': len(video_urls),
            'downloaded': sum(1 for v in download_results.values() if v),
            'failed': sum(1 for v in download_results.values() if not v),
            'links_file': str(links_file) if links_file else None,
            'results': download_results
        }
