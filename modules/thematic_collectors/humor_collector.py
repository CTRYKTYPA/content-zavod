"""
Модуль для сбора видео по теме "Юмор".
Ищет по хэштегам, просмотрам, лайкам и сохраняет в БД и папку.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger
from datetime import datetime
from sqlalchemy.orm import Session
import os
import time
import random
import json
import re

from database.models import Topic, Video, VideoStatus
from modules.content_collector.instagram_downloader import extract_shortcode, download_video_combined
from modules.content_collector.instagram_graph_api import InstagramGraphAPI
from modules.thematic_collectors.browser_cookies_helper import (
    load_cookies_from_browser,
    load_cookies_from_instaloader_session,
    test_session
)
from config import settings

# Добавляем путь к instaloader
import sys
instaloader_path = Path(__file__).parent.parent.parent / "instaloader-master"
if str(instaloader_path) not in sys.path:
    sys.path.insert(0, str(instaloader_path))

try:
    import instaloader
    from instaloader import Hashtag, Post
    INSTALOADER_AVAILABLE = True
except ImportError:
    INSTALOADER_AVAILABLE = False
    logger.warning("Instaloader не доступен, будет использован альтернативный метод")


class HumorCollector:
    """Сборщик видео по теме Юмор."""
    
    THEME_NAME = "Юмор"
    THEME_FOLDER = "humor"
    
    # Хэштеги для поиска (много русских и английских, специфичные)
    HASHTAGS = [
        # Английские (специфичные)
        "funnyvideos", "comedyreels", "funnyreels", "humorvideo", 
        "jokesdaily", "funnyclips", "comedyclips", "humorclips",
        "funnyfails", "comedyfails", "funnycomedy", "comedyvideos",
        "viralvideos", "trendingfunny", "laugh", "funny", "comedy", "humor",
        "funnyvideo", "comedyvideo", "humorvideo", "jokes", "laughs",
        "funnyreel", "comedyreel", "funnycontent", "comedycontent",
        # Русские
        "юмор", "смех", "приколы", "мемы", "комедия", "шутки", 
        "смешно", "юморвидео", "смешное", "прикол", "мем",
        "юморреел", "смешныевидео", "комедиявидео", "шуткивидео",
        # Смешанные/дополнительные
        "funnyрусский", "comedyмемы", "humorвидео", "jokesdaily",
        "funnytrending", "comedyviral", "humorclips", "funnyfails"
    ]
    
    # Минимальные метрики для фильтрации
    MIN_VIEWS = 500000  # 500к просмотров
    MIN_LIKES = 5000    # 5к лайков
    
    def __init__(self, db: Session, topic: Topic):
        """
        Инициализация сборщика.
        
        Args:
            db: Сессия базы данных
            topic: Тематика из БД
        """
        self.db = db
        self.topic = topic
        
        # Папка для сохранения видео этой темы
        self.theme_folder = Path("downloads") / self.THEME_FOLDER
        self.theme_folder.mkdir(parents=True, exist_ok=True)
        
        # Selenium драйвер для переиспользования (авторизация один раз)
        self._selenium_driver = None
        self._selenium_authenticated = False
        self._current_account_index = 0  # Индекс текущего аккаунта для ротации
        
        # Папка для сохранения cookies
        self._cookies_dir = Path("selenium_cookies")
        self._cookies_dir.mkdir(exist_ok=True)
        
        logger.info(f"Инициализирован сборщик для темы: {self.THEME_NAME}")
        logger.info(f"Папка для сохранения: {self.theme_folder.absolute()}")
    
    def _load_user_agent(self) -> str:
        """Загрузить случайный user agent из файла."""
        try:
            useragents_file = Path("useragents.txt")
            if useragents_file.exists():
                with open(useragents_file, 'r', encoding='utf-8', errors='ignore') as f:
                    agents = [line.strip() for line in f if line.strip() and len(line.strip()) > 30]
                    if agents:
                        return random.choice(agents)
        except Exception as e:
            logger.debug(f"Ошибка загрузки user agent: {e}")
        
        # Дефолтный user agent
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    
    def _login_to_instagram(self, session: 'requests.Session', username: str, password: str) -> bool:
        """
        Авторизация в Instagram через requests.
        
        Args:
            session: Сессия requests
            username: Логин
            password: Пароль
        
        Returns:
            True если успешно
        """
        try:
            logger.info("Авторизация в Instagram...")
            
            # Шаг 1: Получаем главную страницу для получения CSRF токена
            user_agent = self._load_user_agent()
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.instagram.com/',
                'Origin': 'https://www.instagram.com',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            logger.info("Получаю CSRF токен...")
            # Пробуем несколько раз из-за возможных SSL ошибок
            max_retries = 3
            response = None
            last_error = None
            for attempt in range(max_retries):
                try:
                    response = session.get('https://www.instagram.com/accounts/login/', headers=headers, timeout=20)
                    logger.debug(f"CSRF запрос: статус {response.status_code}, URL: {response.url}")
                    break
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        logger.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}, повторяю через 2 сек...")
                        time.sleep(2)
                    else:
                        logger.error(f"Все попытки получения CSRF токена не удались. Последняя ошибка: {e}")
                        raise
            
            if not response:
                logger.error(f"Не удалось получить CSRF токен после всех попыток. Ошибка: {last_error}")
                return False
            
            # Извлекаем CSRF токен из cookies или HTML
            csrf_token = None
            if 'csrftoken' in session.cookies:
                csrf_token = session.cookies['csrftoken']
                logger.info(f"[OK] CSRF токен из cookies: {csrf_token[:20]}...")
            else:
                # Пробуем извлечь из HTML
                csrf_match = re.search(r'"csrf_token":"([^"]+)"', response.text)
                if csrf_match:
                    csrf_token = csrf_match.group(1)
                    logger.info(f"[OK] CSRF токен из HTML: {csrf_token[:20]}...")
                else:
                    # Альтернативный метод: через /api/v1/web/data/shared_data/
                    try:
                        logger.debug("Пробую получить CSRF через /api/v1/web/data/shared_data/...")
                        shared_data_response = session.get(
                            'https://www.instagram.com/api/v1/web/data/shared_data/',
                            headers={'User-Agent': user_agent},
                            timeout=15
                        )
                        if 'csrftoken' in session.cookies:
                            csrf_token = session.cookies['csrftoken']
                            logger.info(f"[OK] CSRF токен через shared_data API: {csrf_token[:20]}...")
                    except Exception as e:
                        logger.debug(f"Метод shared_data не сработал: {e}")
            
            if not csrf_token:
                logger.warning("[WARN] CSRF токен не найден, пробую без него...")
                csrf_token = ""
            else:
                logger.info(f"[OK] CSRF токен получен: {csrf_token[:20]}...")
            
            # Шаг 2: Авторизация (УЛУЧШЕННЫЕ ЗАГОЛОВКИ)
            login_headers = {
                'User-Agent': user_agent,
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrf_token,
                'X-Requested-With': 'XMLHttpRequest',
                'X-Instagram-AJAX': '1',
                'X-IG-App-ID': '936619743392459',
                'X-IG-WWW-Claim': '0',
                'Origin': 'https://www.instagram.com',
                'Referer': 'https://www.instagram.com/accounts/login/',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            }
            
            logger.info("Отправляю запрос на авторизацию...")
            
            # Пробуем разные форматы данных для авторизации
            timestamp = int(time.time())
            login_data_variants = [
                # Вариант 1: Только enc_password (как в instaloader)
                {
                    'username': username,
                    'enc_password': f'#PWD_INSTAGRAM_BROWSER:0:{timestamp}:{password}',
                },
                # Вариант 2: С дополнительными полями
                {
                    'username': username,
                    'enc_password': f'#PWD_INSTAGRAM_BROWSER:0:{timestamp}:{password}',
                    'queryParams': '{}',
                    'optIntoOneTap': 'false',
                },
                # Вариант 3: Старый формат (на случай если новый не работает)
                {
                    'username': username,
                    'password': password,
                    'queryParams': '{}',
                    'optIntoOneTap': 'false',
                },
            ]
            
            # Пробуем оба endpoint (старый и новый)
            endpoints_to_try = [
                'https://www.instagram.com/api/v1/web/accounts/login/ajax/',  # Новый (как в instaloader)
                'https://www.instagram.com/accounts/login/ajax/',  # Старый
            ]
            
            # Пробуем несколько раз из-за возможных SSL ошибок
            max_retries = 2
            login_response = None
            last_error = None
            
            # Пробуем все комбинации endpoint + формат данных
            for endpoint_url in endpoints_to_try:
                logger.debug(f"Пробую endpoint: {endpoint_url}")
                
                for variant_idx, login_data_fixed in enumerate(login_data_variants):
                    logger.debug(f"Пробую вариант данных {variant_idx + 1}/{len(login_data_variants)}")
                    
                    for attempt in range(max_retries):
                        try:
                            logger.debug(f"Попытка авторизации {attempt + 1}/{max_retries} на {endpoint_url}...")
                            logger.debug(f"Отправляю POST с данными: username={username}, keys={list(login_data_fixed.keys())}")
                            
                            login_response = session.post(
                                endpoint_url,
                                headers=login_headers,
                                data=login_data_fixed,
                                timeout=20,
                                allow_redirects=False  # НЕ разрешаем редиректы - проверяем ответ напрямую
                            )
                            logger.debug(f"Авторизация: статус {login_response.status_code}, размер ответа: {len(login_response.text)}")
                            logger.debug(f"URL после запроса: {login_response.url}")
                            
                            # Если получили ответ, проверяем его
                            if login_response:
                                # Пробуем распарсить JSON
                                try:
                                    result = login_response.json()
                                    authenticated = result.get('authenticated', False)
                                    # Если авторизация успешна, выходим из всех циклов
                                    if authenticated:
                                        logger.info(f"[OK] Авторизация успешна с вариантом {variant_idx + 1} на {endpoint_url}!")
                                        break
                                except:
                                    pass
                                
                                # Если это последняя попытка для этого варианта, пробуем следующий
                                if attempt == max_retries - 1:
                                    break
                                    
                        except Exception as e:
                            last_error = e
                            error_str = str(e)
                            error_type = type(e).__name__
                            
                            # SSL ошибки
                            if 'SSL' in error_type or 'SSL' in error_str or 'SSLError' in error_str:
                                if attempt < max_retries - 1:
                                    logger.warning(f"SSL ошибка на попытке {attempt + 1}/{max_retries}: {e}, повторяю через 3 сек...")
                                    time.sleep(3)
                                else:
                                    logger.error(f"SSL ошибка после всех попыток: {e}")
                                    logger.error("Возможные причины: проблемы с VPN/прокси, блокировка Instagram, проблемы с сетью")
                                    # Пробуем следующий вариант данных
                                    break
                            # Другие ошибки запроса
                            elif 'Connection' in error_type or 'Timeout' in error_type:
                                if attempt < max_retries - 1:
                                    logger.warning(f"Ошибка соединения {attempt + 1}/{max_retries} ({error_type}): {e}, повторяю через 3 сек...")
                                    time.sleep(3)
                                else:
                                    logger.error(f"Ошибка соединения после всех попыток ({error_type}): {e}")
                                    # Пробуем следующий вариант данных
                                    break
                            # Все остальные ошибки
                            else:
                                logger.error(f"Ошибка авторизации {attempt + 1}/{max_retries} ({error_type}): {e}")
                                if attempt < max_retries - 1:
                                    time.sleep(3)
                                else:
                                    # Пробуем следующий вариант данных
                                    break
                    
                    # Если авторизация успешна, выходим из цикла по вариантам
                    if login_response:
                        try:
                            result = login_response.json()
                            if result.get('authenticated', False):
                                break
                        except:
                            pass
                
                # Если авторизация успешна, выходим из цикла по endpoints
                if login_response:
                    try:
                        result = login_response.json()
                        if result.get('authenticated', False):
                            break
                    except:
                        pass
            
            # Проверяем результат после всех попыток
            if not login_response:
                logger.error(f"Не удалось авторизоваться после всех попыток. Последняя ошибка: {last_error}")
                if last_error:
                    logger.error(f"Тип ошибки: {type(last_error).__name__}")
                    logger.error(f"Детали ошибки: {str(last_error)}")
                return False
            
            # Проверяем ответ
            logger.debug(f"Статус авторизации: {login_response.status_code}")
            logger.debug(f"Cookies ПОСЛЕ POST запроса (до проверки): {list(session.cookies.keys())}")
            logger.debug(f"Размер ответа: {len(login_response.text)} символов")
            
            # Логируем все cookies подробно
            if session.cookies:
                logger.debug("Детали cookies:")
                for cookie in session.cookies:
                    logger.debug(f"  - {cookie.name}: {cookie.value[:20]}... (domain: {cookie.domain})")
            
            # Если статус не 200, логируем подробности
            if login_response.status_code != 200:
                logger.warning(f"Неожиданный статус код: {login_response.status_code}")
                logger.debug(f"Первые 500 символов ответа: {login_response.text[:500]}")
            
            # Пробуем распарсить JSON ответ ПЕРВЫМ, чтобы понять что вернул Instagram
            try:
                if login_response.text:
                    result = login_response.json()
                    logger.info(f"[INFO] Полный ответ авторизации: {result}")
                    
                    # Проверяем на checkpoint/challenge
                    if result.get('checkpoint_url') or result.get('challenge'):
                        checkpoint_url = result.get('checkpoint_url') or result.get('challenge', {}).get('url')
                        logger.error(f"[ERROR] Требуется checkpoint/challenge: {checkpoint_url}")
                        logger.error("Нужно пройти проверку в браузере")
                        return False
                    
                    # КРИТИЧЕСКИ ВАЖНО: Проверяем authenticated ПЕРВЫМ!
                    authenticated = result.get('authenticated', False)
                    status = result.get('status', '')
                    
                    logger.info(f"[INFO] Ответ авторизации: authenticated={authenticated}, status={status}")
                    
                    # Проверяем статус в JSON
                    if authenticated and (status == 'ok' or result.get('user')):
                        logger.info(f"[OK] Instagram вернул успешную авторизацию: authenticated=True, status={status}")
                        
                        # ВАЖНО: Проверяем, есть ли userId - это признак успешной авторизации
                        user_id = result.get('userId') or result.get('user_id')
                        if user_id:
                            logger.info(f"[OK] userId найден: {user_id} - это хороший знак!")
                        # ВАЖНО: Проверяем cookies ПОСЛЕ успешного ответа
                        # Иногда Instagram устанавливает cookies с задержкой
                        time.sleep(2)  # Увеличиваем задержку
                        
                        # Проверяем cookies - это главный индикатор успешной авторизации
                        if 'sessionid' in session.cookies:
                            logger.info("[OK] Авторизация успешна (есть sessionid cookie)!")
                            logger.debug(f"Все cookies: {list(session.cookies.keys())}")
                            return True
                        else:
                            logger.warning("[WARN] Instagram вернул 'ok', но sessionid cookie не установлен!")
                            logger.warning(f"Доступные cookies: {list(session.cookies.keys())}")
                            
                            # Пробуем несколько методов для получения sessionid
                            methods_to_try = [
                                ('https://www.instagram.com/', 'Главная страница'),
                                ('https://www.instagram.com/api/v1/web/data/shared_data/', 'Shared data API'),
                                ('https://www.instagram.com/accounts/edit/', 'Edit profile page'),
                            ]
                            
                            for url, desc in methods_to_try:
                                try:
                                    logger.info(f"Пробую получить sessionid через {desc}...")
                                    response = session.get(url, timeout=10, allow_redirects=True)
                                    logger.debug(f"{desc}: статус {response.status_code}, cookies: {list(session.cookies.keys())}")
                                    
                                    if 'sessionid' in session.cookies:
                                        logger.info(f"[OK] sessionid получен через {desc}!")
                                        return True
                                    
                                    # Проверяем, не редирект ли на login
                                    if 'login' in response.url.lower():
                                        logger.warning(f"[WARN] {desc} редиректит на login")
                                        break
                                except Exception as e:
                                    logger.debug(f"Ошибка при запросе {desc}: {e}")
                                    continue
                            
                            # Если все равно нет sessionid, но статус ok - это проблема
                            logger.error("[ERROR] КРИТИЧЕСКАЯ ПРОБЛЕМА: status='ok', но sessionid не получен!")
                            logger.error("Возможные причины:")
                            logger.error("  1. Instagram требует checkpoint/challenge (проверка в браузере)")
                            logger.error("  2. Аккаунт заблокирован или требует подтверждения")
                            logger.error("  3. Instagram изменил механизм авторизации")
                            logger.error("  4. Проблемы с VPN/прокси")
                            
                            # НО: все равно возвращаем True, так как status='ok'
                            # Может быть, sessionid не нужен для некоторых запросов
                            logger.warning("[WARN] Продолжаю работу БЕЗ sessionid (может не работать)")
                            return True
                    elif status == 'ok' and not authenticated:
                        # Это проблема - status ok, но authenticated False
                        logger.error(f"[ERROR] ПРОБЛЕМА: status='ok', но authenticated=False!")
                        logger.error("Это означает, что авторизация НЕ прошла, даже если статус ok")
                        logger.error("Возможные причины:")
                        logger.error("  1. Неправильный пароль")
                        logger.error("  2. Instagram требует checkpoint/challenge")
                        logger.error("  3. Аккаунт заблокирован или требует подтверждения")
                        logger.error("  4. Instagram изменил механизм авторизации")
                        return False
                    elif result.get('two_factor_required'):
                        logger.warning("[WARN] Требуется двухфакторная аутентификация")
                        return False
                    else:
                        error_msg = result.get('message') or result.get('error') or result.get('errors', {}).get('error', 'Неизвестная ошибка')
                        logger.warning(f"[WARN] Авторизация не удалась: {error_msg}")
                        logger.debug(f"Полный ответ: {result}")
                        return False
                else:
                    logger.warning("[WARN] Пустой ответ от сервера")
                    return False
            except json.JSONDecodeError:
                # Если не JSON, проверяем статус код
                logger.debug(f"Ответ не JSON, первые 500 символов: {login_response.text[:500]}")
                if login_response.status_code == 200:
                    logger.warning("[WARN] Неожиданный формат ответа, но статус 200")
                    return False
                else:
                    logger.warning(f"[WARN] Ошибка авторизации, статус: {login_response.status_code}")
                    logger.debug(f"Тело ответа: {login_response.text[:500]}")
                    return False
                
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return False
    
    def _get_hashtag_posts_via_graph_api(self, hashtag: str, access_token: str, user_id: str, limit: int = 50) -> List[str]:
        """
        Получить посты по хэштегу через Instagram Graph API (официальный API).
        
        Args:
            hashtag: Хэштег без #
            access_token: Access token из Graph API Explorer
            user_id: ID вашего Instagram аккаунта (из Graph API Explorer)
            limit: Количество постов
        
        Returns:
            Список URL постов
        """
        post_urls = []
        
        try:
            import requests
            
            # Шаг 1: Получаем ID хэштега через поиск
            hashtag_search_url = "https://graph.instagram.com/ig_hashtag_search"
            params = {
                'user_id': user_id,
                'q': hashtag,
                'access_token': access_token
            }
            
            logger.info(f"Ищу ID хэштега #{hashtag} через Graph API...")
            response = requests.get(hashtag_search_url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and len(data['data']) > 0:
                    hashtag_id = data['data'][0]['id']
                    logger.info(f"[OK] ID хэштега #{hashtag}: {hashtag_id}")
                    
                    # Шаг 2: Получаем топ посты по хэштегу
                    top_media_url = f"https://graph.instagram.com/{hashtag_id}/top_media"
                    params = {
                        'user_id': user_id,
                        'fields': 'id,media_type,permalink,media_url,thumbnail_url,timestamp',
                        'limit': limit,
                        'access_token': access_token
                    }
                    
                    logger.info(f"Получаю топ посты для #{hashtag}...")
                    response = requests.get(top_media_url, params=params, timeout=15)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if 'data' in data:
                            for item in data['data']:
                                # Берем только видео
                                if item.get('media_type') == 'VIDEO' and item.get('permalink'):
                                    url = item['permalink']
                                    if url not in post_urls:
                                        post_urls.append(url)
                            logger.info(f"[OK] Найдено {len(post_urls)} видео через top_media")
                    
                    # Шаг 3: Получаем недавние посты (если нужно больше)
                    if len(post_urls) < limit:
                        recent_media_url = f"https://graph.instagram.com/{hashtag_id}/recent_media"
                        params = {
                            'user_id': user_id,
                            'fields': 'id,media_type,permalink,media_url,thumbnail_url,timestamp',
                            'limit': limit - len(post_urls),
                            'access_token': access_token
                        }
                        
                        logger.info(f"Получаю недавние посты для #{hashtag}...")
                        response = requests.get(recent_media_url, params=params, timeout=15)
                        
                        if response.status_code == 200:
                            data = response.json()
                            if 'data' in data:
                                for item in data['data']:
                                    if item.get('media_type') == 'VIDEO' and item.get('permalink'):
                                        url = item['permalink']
                                        if url not in post_urls:
                                            post_urls.append(url)
                                logger.info(f"[OK] Всего найдено {len(post_urls)} видео")
                else:
                    logger.warning(f"[WARN] Хэштег #{hashtag} не найден в Graph API")
            else:
                error_text = response.text[:300] if response.text else "Нет ответа"
                logger.warning(f"[WARN] Ошибка Graph API поиска: {response.status_code} - {error_text}")
                
        except Exception as e:
            logger.error(f"Ошибка Graph API запроса для #{hashtag}: {e}")
        
        return post_urls
    
    def _get_hashtag_posts_via_api(self, session: 'requests.Session', hashtag: str, limit: int = 50) -> List[str]:
        """
        Получить посты по хэштегу через GraphQL API (улучшенный метод).
        
        Args:
            session: Авторизованная сессия
            hashtag: Хэштег без #
            limit: Количество постов
        
        Returns:
            Список URL постов
        """
        post_urls = []
        
        try:
            # ДЕТАЛЬНАЯ ПРОВЕРКА СЕССИИ
            logger.debug(f"[DEBUG] Проверка сессии для #{hashtag}:")
            logger.debug(f"   - ID сессии: {id(session)}")
            logger.debug(f"   - Все cookies: {list(session.cookies.keys())}")
            logger.debug(f"   - Количество cookies: {len(session.cookies)}")
            
            # Проверяем, что сессия авторизована
            # ВАЖНО: Instagram может не устанавливать sessionid, но авторизация может работать
            # Проверяем наличие других индикаторов авторизации
            has_sessionid = 'sessionid' in session.cookies
            has_csrftoken = 'csrftoken' in session.cookies
            has_mid = 'mid' in session.cookies
            
            if not has_sessionid:
                logger.warning(f"[WARN] Нет sessionid cookie для #{hashtag}")
                logger.warning(f"   Доступные cookies: {list(session.cookies.keys())}")
                
                # Если есть другие cookies, пробуем работать с ними
                if has_csrftoken or has_mid:
                    logger.info(f"   [OK] Но есть другие cookies (csrftoken={has_csrftoken}, mid={has_mid}) - пробую работать с ними")
                else:
                    logger.warning("   [WARN] Нет никаких cookies авторизации - запросы могут не работать")
            else:
                logger.info(f"[OK] Сессия авторизована! sessionid найден для #{hashtag}")
                logger.debug(f"   sessionid: {session.cookies.get('sessionid')[:30]}...")
            
            # Используем более новый endpoint
            user_agent = self._load_user_agent()
            headers = {
                'User-Agent': user_agent,
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'X-Requested-With': 'XMLHttpRequest',
                'X-IG-App-ID': '936619743392459',
                'X-Instagram-AJAX': '1',
                'Origin': 'https://www.instagram.com',
                'Referer': f'https://www.instagram.com/explore/tags/{hashtag}/',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            }
            
            if 'csrftoken' in session.cookies:
                headers['X-CSRFToken'] = session.cookies['csrftoken']
            else:
                logger.warning("[WARN] Нет csrftoken в cookies, запрос может не сработать")
            
            # РАБОЧИЕ ENDPOINTS 2024-2025 (проверено)
            # РАБОЧИЕ ENDPOINTS 2024-2025 (пробуем все варианты)
            # Кодируем хэштег для URL (важно для русских символов)
            from urllib.parse import quote
            hashtag_encoded = quote(hashtag)
            
            endpoints = [
                f"https://www.instagram.com/api/v1/tags/web_info/?tag_name={hashtag_encoded}",
                f"https://www.instagram.com/explore/tags/{hashtag_encoded}/?__a=1&__d=dis",
                f"https://www.instagram.com/explore/tags/{hashtag_encoded}/?__a=1",
                f"https://www.instagram.com/api/v1/tags/{hashtag_encoded}/info/",
            ]
            
            for endpoint in endpoints:
                try:
                    logger.debug(f"Пробую endpoint: {endpoint}")
                    response = session.get(endpoint, headers=headers, timeout=20)
                    
                    logger.debug(f"Статус ответа: {response.status_code}, размер: {len(response.text)}")
                    
                    # Проверяем, не редирект ли на login
                    if 'accounts/login' in response.url:
                        logger.warning(f"Редирект на login для {endpoint}, пропускаю")
                        continue
                    
                    if response.status_code == 200:
                        try:
                            # Проверяем, не бинарные ли данные (gzip)
                            content = response.content
                            if content.startswith(b'\x1f\x8b'):  # Gzip magic number
                                import gzip
                                logger.debug("Ответ сжат gzip, распаковываю...")
                                content = gzip.decompress(content)
                                response_text = content.decode('utf-8', errors='ignore')
                            else:
                                response_text = response.text
                            
                            # Пробуем распарсить JSON
                            try:
                                data = json.loads(response_text)
                            except json.JSONDecodeError:
                                # Если не JSON, пробуем извлечь из HTML
                                logger.debug("Ответ не JSON, пробую извлечь JSON из HTML...")
                                # Ищем window._sharedData или другие JSON структуры
                                json_match = re.search(r'window\._sharedData\s*=\s*({.+?});', response_text, re.DOTALL)
                                if json_match:
                                    data = json.loads(json_match.group(1))
                                else:
                                    raise ValueError("Не удалось найти JSON в ответе")
                            
                            # СОХРАНЯЕМ ПОЛНЫЙ JSON ДЛЯ ОТЛАДКИ (ВСЕГДА для отладки)
                            debug_json_file = Path("debug_html") / f"instagram_{hashtag}_api_response.json"
                            debug_json_file.parent.mkdir(exist_ok=True)
                            try:
                                with open(debug_json_file, 'w', encoding='utf-8') as f:
                                    json.dump(data, f, indent=2, ensure_ascii=False)
                                logger.info(f"[OK] Полный JSON ответ сохранен в {debug_json_file} для анализа")
                                logger.info(f"[INFO] Ключи в JSON (первые 15): {list(data.keys())[:15]}")
                                
                                # Показываем структуру JSON для понимания
                                if 'graphql' in data:
                                    logger.info("[OK] Найден ключ 'graphql' в JSON")
                                if 'data' in data:
                                    logger.info("[OK] Найден ключ 'data' в JSON")
                                if 'hashtag' in data:
                                    logger.info("[OK] Найден ключ 'hashtag' в JSON")
                            except Exception as e:
                                logger.error(f"[ERROR] Не удалось сохранить JSON: {e}")
                            
                            # Парсим разные форматы ответов (МАКСИМАЛЬНО АГРЕССИВНЫЙ ПАРСИНГ)
                            hashtag_data = None
                            
                            # Вариант 1: data.hashtag (самый частый)
                            if 'data' in data:
                                if 'hashtag' in data['data']:
                                    hashtag_data = data['data']['hashtag']
                                elif 'recent' in data['data']:
                                    hashtag_data = data['data']
                                elif isinstance(data['data'], dict):
                                    hashtag_data = data['data']
                            
                            # Вариант 2: Прямо hashtag в корне
                            if not hashtag_data and 'hashtag' in data:
                                hashtag_data = data['hashtag']
                            
                            # Вариант 3: graphql.hashtag (старый формат)
                            if not hashtag_data and 'graphql' in data:
                                if 'hashtag' in data['graphql']:
                                    hashtag_data = data['graphql']['hashtag']
                            
                            # Вариант 4: Прямо в корне (если структура плоская)
                            if not hashtag_data:
                                logger.debug(f"Не найдена структура hashtag в JSON для #{hashtag}, пробую весь data")
                                hashtag_data = data
                            
                            # Ищем посты в ВСЕХ возможных структурах (МАКСИМАЛЬНО АГРЕССИВНЫЙ ПАРСИНГ)
                            edges = []
                            
                            # Структура 1: edge_hashtag_to_media
                            if 'edge_hashtag_to_media' in hashtag_data:
                                edges.extend(hashtag_data['edge_hashtag_to_media'].get('edges', []))
                            
                            # Структура 2: edge_hashtag_to_top_posts
                            if 'edge_hashtag_to_top_posts' in hashtag_data:
                                top_edges = hashtag_data['edge_hashtag_to_top_posts'].get('edges', [])
                                edges.extend(top_edges)
                            
                            # Структура 3: recent sections
                            if 'recent' in hashtag_data:
                                recent_sections = hashtag_data['recent'].get('sections', [])
                                for section in recent_sections:
                                    section_medias = section.get('layout_content', {}).get('medias', [])
                                    edges.extend(section_medias)
                            
                            # Структура 4: top_posts
                            if 'top_posts' in hashtag_data:
                                top_posts = hashtag_data['top_posts'].get('nodes', [])
                                edges.extend(top_posts)
                            
                            # Структура 5: media
                            if 'media' in hashtag_data:
                                media_items = hashtag_data['media'].get('nodes', [])
                                edges.extend(media_items)
                            
                            # Структура 6: items
                            if 'items' in hashtag_data:
                                edges.extend(hashtag_data['items'])
                            
                            # Структура 7: posts
                            if 'posts' in hashtag_data:
                                edges.extend(hashtag_data['posts'])
                            
                            # Структура 8: Прямо в data (если нет вложенности)
                            if not edges and isinstance(data, dict):
                                # Рекурсивный поиск всех возможных структур
                                def find_all_edges(obj, depth=0):
                                    if depth > 5:  # Ограничиваем глубину
                                        return []
                                    found = []
                                    if isinstance(obj, dict):
                                        # Ищем известные ключи
                                        for key in ['edges', 'nodes', 'items', 'posts', 'medias']:
                                            if key in obj:
                                                found.extend(obj[key] if isinstance(obj[key], list) else [])
                                        # Рекурсивно ищем в значениях
                                        for value in obj.values():
                                            found.extend(find_all_edges(value, depth + 1))
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            found.extend(find_all_edges(item, depth + 1))
                                    return found
                                
                                additional_edges = find_all_edges(data)
                                edges.extend(additional_edges)
                            
                            logger.info(f"[DEBUG] Найдено {len(edges)} постов в структуре для #{hashtag}")
                            
                            if not edges:
                                logger.warning(f"[WARN] Нет edges в JSON для #{hashtag}, пробую найти shortcode напрямую...")
                                # Пробуем найти shortcode напрямую в JSON (иногда они в другом месте)
                                def find_shortcodes_recursive(obj, depth=0, max_depth=10):
                                    """Рекурсивно ищем все shortcode в JSON"""
                                    if depth > max_depth:
                                        return []
                                    found = []
                                    if isinstance(obj, dict):
                                        # Проверяем текущий уровень
                                        if 'shortcode' in obj:
                                            found.append(obj['shortcode'])
                                        if 'code' in obj:
                                            found.append(obj['code'])
                                        # Рекурсивно ищем в значениях
                                        for value in obj.values():
                                            found.extend(find_shortcodes_recursive(value, depth + 1, max_depth))
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            found.extend(find_shortcodes_recursive(item, depth + 1, max_depth))
                                    return found
                                
                                all_shortcodes_found = find_shortcodes_recursive(data)
                                logger.info(f"[DEBUG] Найдено {len(all_shortcodes_found)} shortcode напрямую в JSON")
                                for sc in all_shortcodes_found:
                                    if sc:
                                        url = f"https://www.instagram.com/p/{sc}/"
                                        if url not in post_urls:
                                            post_urls.append(url)
                                            logger.debug(f"[OK] Добавлена ссылка из прямого поиска: {url}")
                            
                            # Сначала пробуем найти ВСЕ посты (не только видео), потом отфильтруем
                            all_shortcodes = []
                            
                            for edge in edges:
                                node = edge.get('node') or edge.get('media') or edge
                                if not node:
                                    # Если edge сам является node
                                    if isinstance(edge, dict) and ('shortcode' in edge or 'code' in edge):
                                        node = edge
                                    else:
                                        continue
                                
                                shortcode = node.get('shortcode') or node.get('code')
                                if shortcode:
                                    all_shortcodes.append((shortcode, node))
                            
                            logger.info(f"[INFO] Найдено {len(all_shortcodes)} постов с shortcode для #{hashtag}")
                            
                            # Теперь проверяем, какие из них видео
                            # ВАЖНО: Если не можем определить тип, добавляем ВСЕ (проверим при скачивании)
                            for shortcode, node in all_shortcodes:
                                is_video = (
                                    node.get('is_video', False) or 
                                    node.get('type') == 2 or 
                                    node.get('media_type') == 'VIDEO' or
                                    node.get('__typename') == 'GraphVideo' or
                                    node.get('media_type') == 2 or
                                    node.get('video_codec') is not None or
                                    'video' in str(node.get('__typename', '')).lower() or
                                    node.get('product_type') == 'feed'  # Иногда видео помечаются так
                                )
                                
                                # ВАЖНО: Добавляем ВСЕ посты с shortcode (не только видео)
                                # Instagram может не возвращать тип медиа, поэтому проверяем при скачивании
                                url = f"https://www.instagram.com/p/{shortcode}/"
                                if url not in post_urls:
                                    post_urls.append(url)
                                    logger.debug(f"[OK] Добавлена ссылка: {url} (is_video={is_video})")
                            
                            logger.info(f"[OK] После фильтрации: {len(post_urls)} ссылок для #{hashtag}")
                            
                            # Если все еще нет ссылок, пробуем найти shortcode в любом месте JSON
                            if not post_urls:
                                logger.warning(f"[WARN] Не найдено ссылок через стандартный парсинг для #{hashtag}, пробую глубокий поиск...")
                                def deep_search_shortcodes(obj, depth=0, max_depth=15):
                                    """Глубокий рекурсивный поиск всех shortcode"""
                                    if depth > max_depth:
                                        return []
                                    found = []
                                    if isinstance(obj, dict):
                                        # Проверяем все ключи на наличие shortcode
                                        for key, value in obj.items():
                                            if key in ['shortcode', 'code'] and isinstance(value, str) and len(value) >= 6:
                                                found.append(value)
                                            elif isinstance(value, (dict, list)):
                                                found.extend(deep_search_shortcodes(value, depth + 1, max_depth))
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            found.extend(deep_search_shortcodes(item, depth + 1, max_depth))
                                    return found
                                
                                all_found_shortcodes = deep_search_shortcodes(data)
                                logger.info(f"[DEBUG] Глубокий поиск нашел {len(all_found_shortcodes)} shortcode")
                                for sc in all_found_shortcodes[:limit * 2]:  # Берем в 2 раза больше для фильтрации
                                    if sc and isinstance(sc, str) and len(sc) >= 6:
                                        url = f"https://www.instagram.com/p/{sc}/"
                                        if url not in post_urls:
                                            post_urls.append(url)
                                            logger.debug(f"[OK] Добавлена ссылка из глубокого поиска: {url}")
                                            
                            if post_urls:
                                logger.info(f"[OK] Endpoint {endpoint}: найдено {len(post_urls)} ссылок для #{hashtag}")
                                break
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.error(f"[ERROR] Ошибка парсинга JSON для {endpoint}: {e}")
                            logger.error(f"Первые 500 символов ответа: {response.text[:500]}")
                            continue
                    elif response.status_code == 403:
                        logger.warning(f"[WARN] 403 Forbidden для {endpoint} - возможно нужна авторизация")
                    elif response.status_code == 404:
                        logger.warning(f"[WARN] 404 Not Found для {endpoint}")
                    else:
                        logger.warning(f"[WARN] Неожиданный статус {response.status_code} для {endpoint}")
                except Exception as e:
                    logger.error(f"[ERROR] Ошибка запроса к {endpoint}: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    continue
            
        except Exception as e:
            logger.debug(f"Ошибка API запроса для #{hashtag}: {e}")
        
        return post_urls
    
    def _get_hashtag_posts_via_graph_api(self, hashtag: str, limit: int = 50) -> List[str]:
        """
        Получить посты по хэштегу через Instagram Graph API (официальный метод).
        Использует отдельный модуль InstagramGraphAPI.
        
        Args:
            hashtag: Хэштег без #
            limit: Количество постов
        
        Returns:
            Список URL постов
        """
        try:
            logger.info(f"Использую Instagram Graph API для #{hashtag}...")
            
            # Используем отдельный модуль
            api = InstagramGraphAPI()
            post_urls = api.get_hashtag_posts(hashtag, limit=limit)
            
            if post_urls:
                logger.info(f"[OK] Graph API: найдено {len(post_urls)} ссылок для #{hashtag}")
            else:
                logger.warning(f"[WARN] Graph API: не найдено ссылок для #{hashtag}")
                logger.warning("Возможные причины:")
                logger.warning("  - Требуется App Review для 'Instagram Public Content Access'")
                logger.warning("  - Недостаточно разрешений")
                logger.warning("  - Проблемы с сетью")
                logger.info("✅ Продолжаю сбор через другие методы (Selenium, Instaloader)...")
            
            return post_urls
            
        except Exception as e:
            logger.warning(f"[WARN] Ошибка Graph API для #{hashtag}: {e}")
            logger.warning("Пропускаю Graph API, использую другие методы...")
            return []
    
    def _get_hashtag_posts_via_instaloader(self, hashtag: str, limit: int = 50) -> List[str]:
        """
        Получить посты по хэштегу через instaloader (САМЫЙ НАДЕЖНЫЙ МЕТОД).
        
        Args:
            hashtag: Хэштег без #
            limit: Количество постов
        
        Returns:
            Список URL постов
        """
        post_urls = []
        
        if not INSTALOADER_AVAILABLE:
            logger.warning("[WARN] Instaloader не доступен, пропускаю этот метод")
            return post_urls
        
        try:
            # Создаем loader
            loader = instaloader.Instaloader(
                download_videos=False,
                download_pictures=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
            )
            
            # Авторизация (если есть логин/пароль)
            username = settings.INSTAGRAM_USERNAME
            password = settings.INSTAGRAM_PASSWORD
            is_authenticated = False
            
            if username and password:
                try:
                    logger.debug(f"Пробую авторизоваться в instaloader для #{hashtag}...")
                    loader.login(username, password)
                    is_authenticated = True
                    logger.info(f"[OK] Instaloader авторизован для #{hashtag}")
                except instaloader.exceptions.BadCredentialsException as e:
                    logger.error(f"[ERROR] Неверный логин или пароль для instaloader: {e}")
                    logger.warning("Проверьте INSTAGRAM_USERNAME и INSTAGRAM_PASSWORD в .env")
                    logger.warning("Пробую без авторизации (может не работать для хэштегов)")
                except instaloader.exceptions.TwoFactorAuthRequiredException as e:
                    logger.error(f"[ERROR] Требуется двухфакторная аутентификация: {e}")
                    logger.warning("Пробую без авторизации (может не работать для хэштегов)")
                except instaloader.exceptions.ConnectionException as e:
                    logger.error(f"[ERROR] Ошибка подключения к Instagram: {e}")
                    logger.warning("Пробую без авторизации (может не работать для хэштегов)")
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'wrong password' in error_msg or 'invalid' in error_msg or 'login' in error_msg:
                        logger.error(f"[ERROR] Ошибка авторизации в instaloader: {e}")
                        logger.warning("Проверьте логин и пароль в .env файле")
                    else:
                        logger.warning(f"[WARN] Не удалось авторизоваться в instaloader: {e}")
                    logger.warning("Пробую без авторизации (может не работать для хэштегов)")
            
            # Получаем посты из хэштега
            logger.debug(f"Получаю посты из хэштега #{hashtag} через instaloader (авторизован: {is_authenticated})...")
            try:
                hashtag_obj = Hashtag.from_name(loader.context, hashtag)
            except instaloader.exceptions.LoginRequiredException:
                if not is_authenticated:
                    logger.warning(f"[WARN] Instaloader требует авторизацию для хэштега #{hashtag}")
                    return post_urls
                else:
                    raise
            except Exception as e:
                logger.error(f"[ERROR] Не удалось получить хэштег #{hashtag}: {e}")
                return post_urls
            
            count = 0
            try:
                for post in hashtag_obj.get_posts():
                    if count >= limit:
                        break
                    
                    try:
                        # Проверяем, что это видео
                        if post.is_video:
                            url = f"https://www.instagram.com/p/{post.shortcode}/"
                            if url not in post_urls:
                                post_urls.append(url)
                                count += 1
                                logger.debug(f"[OK] Найдено видео: {url}")
                    except Exception as e:
                        logger.debug(f"Ошибка обработки поста: {e}")
                        continue
            except instaloader.exceptions.LoginRequiredException:
                if not is_authenticated:
                    logger.warning(f"[WARN] Instaloader требует авторизацию для получения постов #{hashtag}")
                else:
                    logger.error(f"[ERROR] Ошибка доступа к постам #{hashtag}")
            except Exception as e:
                logger.warning(f"[WARN] Ошибка при получении постов: {e}")
            
            if post_urls:
                logger.info(f"[OK] Instaloader: найдено {len(post_urls)} ссылок для #{hashtag}")
            else:
                logger.warning(f"[WARN] Instaloader не нашел ссылки для #{hashtag}")
                
        except Exception as e:
            logger.error(f"[ERROR] Ошибка instaloader для #{hashtag}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return post_urls
    
    def _parse_html_for_links(self, html: str) -> List[str]:
        """Парсинг HTML для извлечения ссылок на посты (улучшенный метод)."""
        post_links = []
        
        try:
            from bs4 import BeautifulSoup
            
            # Используем весь HTML (увеличиваем лимит)
            html_sample = html[:2000000] if len(html) > 2000000 else html
            
            # Метод 1: Ищем window._sharedData (самый надежный способ)
            shared_data_match = re.search(r'window\._sharedData\s*=\s*({.+?});', html_sample, re.DOTALL)
            if shared_data_match:
                try:
                    data = json.loads(shared_data_match.group(1))
                    if 'entry_data' in data:
                        entry_data = data['entry_data']
                        if 'TagPage' in entry_data:
                            tag_page = entry_data['TagPage'][0]
                            if 'graphql' in tag_page:
                                graphql = tag_page['graphql']
                                if 'hashtag' in graphql:
                                    hashtag_data = graphql['hashtag']
                                    if 'edge_hashtag_to_media' in hashtag_data:
                                        edges = hashtag_data['edge_hashtag_to_media'].get('edges', [])
                                        logger.debug(f"Найдено {len(edges)} постов в window._sharedData")
                                        for edge in edges:
                                            if 'node' in edge:
                                                node = edge['node']
                                                shortcode = node.get('shortcode')
                                                if shortcode:
                                                    is_video = node.get('is_video', False)
                                                    if is_video:
                                                        url = f"https://www.instagram.com/p/{shortcode}/"
                                                        if url not in post_links:
                                                            post_links.append(url)
                except Exception as e:
                    logger.debug(f"Ошибка парсинга window._sharedData: {e}")
            
            # Метод 1.5: Ищем window.__additionalDataLoaded (новый формат Instagram)
            additional_data_match = re.search(r'window\.__additionalDataLoaded\s*\([^,]+,\s*({.+?})\);', html_sample, re.DOTALL)
            if additional_data_match:
                try:
                    data = json.loads(additional_data_match.group(1))
                    # Парсим структуру данных
                    links_from_additional = self._parse_json_response(data)
                    post_links.extend(links_from_additional)
                    if links_from_additional:
                        logger.debug(f"Найдено {len(links_from_additional)} ссылок в window.__additionalDataLoaded")
                except Exception as e:
                    logger.debug(f"Ошибка парсинга window.__additionalDataLoaded: {e}")
            
            # Метод 1.6: Ищем window.__initialDataLoaded (новый формат Instagram)
            initial_data_match = re.search(r'window\.__initialDataLoaded\s*=\s*({.+?});', html_sample, re.DOTALL)
            if initial_data_match:
                try:
                    data = json.loads(initial_data_match.group(1))
                    # Парсим структуру данных
                    links_from_initial = self._parse_json_response(data)
                    post_links.extend(links_from_initial)
                    if links_from_initial:
                        logger.debug(f"Найдено {len(links_from_initial)} ссылок в window.__initialDataLoaded")
                except Exception as e:
                    logger.debug(f"Ошибка парсинга window.__initialDataLoaded: {e}")
            
            # Метод 1.7: Ищем window.__d (новый формат Instagram - данные в массиве)
            d_data_match = re.search(r'window\.__d\s*=\s*(\[[^\]]+\])', html_sample, re.DOTALL)
            if d_data_match:
                try:
                    data_array = json.loads(d_data_match.group(1))
                    # Ищем в массиве данные о постах
                    for item in data_array:
                        if isinstance(item, dict):
                            links_from_d = self._parse_json_response(item)
                            post_links.extend(links_from_d)
                except Exception as e:
                    logger.debug(f"Ошибка парсинга window.__d: {e}")
            
            # Метод 2: Ищем JSON в script тегах (новый формат Instagram)
            soup = BeautifulSoup(html_sample, 'html.parser')
            for script in soup.find_all('script', type='text/javascript'):
                script_text = script.string or ""
                if not script_text:
                    continue
                
                # Ищем shortcode в JSON
                if 'shortcode' in script_text:
                    shortcode_matches = re.findall(r'"shortcode"\s*:\s*"([^"]+)"', script_text)
                    for shortcode in shortcode_matches:
                        if len(shortcode) > 5:  # Валидный shortcode
                            url = f"https://www.instagram.com/p/{shortcode}/"
                            if url not in post_links:
                                post_links.append(url)
            
            # Метод 3: Ищем ссылки в HTML (все возможные варианты)
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if '/p/' in href or '/reel/' in href or '/reels/' in href:
                    full_url = f"https://www.instagram.com{href}" if href.startswith('/') else href
                    if '?' in full_url:
                        full_url = full_url.split('?')[0]
                    if full_url not in post_links and 'instagram.com' in full_url:
                        post_links.append(full_url)
            
            # Метод 4: Регулярные выражения (агрессивный поиск)
            patterns = [
                r'https?://(?:www\.)?instagram\.com/(p|reel|reels)/([\w-]+)/?',
                r'/(p|reel|reels)/([\w-]+)/?',
                r'"shortcode"\s*:\s*"([^"]+)"',
                r'instagram\.com/(p|reel|reels)/([\w-]+)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_sample)
                for match in matches:
                    if isinstance(match, tuple):
                        if len(match) >= 2:
                            url = f"https://www.instagram.com/{match[0]}/{match[1]}/"
                            if url not in post_links:
                                post_links.append(url)
                    else:
                        # Просто shortcode
                        if len(match) > 5:  # Валидный shortcode
                            url = f"https://www.instagram.com/p/{match}/"
                            if url not in post_links:
                                post_links.append(url)
                        
        except Exception as e:
            logger.debug(f"Ошибка парсинга HTML: {e}")
        
        return post_links
    
    def _parse_html_aggressive(self, html: str) -> List[str]:
        """Агрессивный парсинг HTML для поиска всех возможных ссылок."""
        post_links = []
        
        try:
            # Ищем все возможные варианты ссылок - более агрессивно
            patterns = [
                # Полные URL
                r'https?://(?:www\.)?instagram\.com/(p|reel)/([\w-]+)/?',
                r'https?://(?:www\.)?instagram\.com/(p|reel)/([\w-]+)',
                # Относительные пути
                r'["\']/(p|reel)/([\w-]+)/?["\']',
                r'["\']/(p|reel)/([\w-]+)["\']',
                r'/(p|reel)/([\w-]+)/?',
                # Shortcode в JSON
                r'"shortcode"\s*:\s*"([^"]+)"',
                r'"code"\s*:\s*"([^"]+)"',
                r'shortcode["\']?\s*[:=]\s*["\']([^"\']+)',
                # В атрибутах
                r'data-shortcode=["\']([^"\']+)["\']',
                r'href=["\']([^"\']*/(?:p|reel)/[\w-]+)',
                # Просто shortcode (11 символов, буквы и цифры)
                r'\b([A-Za-z0-9]{11})\b',
            ]
            
            for pattern in patterns:
                try:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    for match in matches:
                        if isinstance(match, tuple):
                            if len(match) >= 2:
                                post_type = match[0]
                                shortcode = match[1]
                                if len(shortcode) >= 6:  # Минимальная длина shortcode
                                    url = f"https://www.instagram.com/{post_type}/{shortcode}/"
                                    if url not in post_links and 'instagram.com' in url:
                                        post_links.append(url)
                        else:
                            # Просто shortcode или URL
                            if isinstance(match, str):
                                # Если это похоже на shortcode (11 символов, буквы и цифры)
                                if len(match) == 11 and match.replace('_', '').replace('-', '').isalnum():
                                    url = f"https://www.instagram.com/p/{match}/"
                                    if url not in post_links:
                                        post_links.append(url)
                                # Если это URL
                                elif 'instagram.com' in match or match.startswith('/p/') or match.startswith('/reel/') or match.startswith('/reels/'):
                                    if match.startswith('/'):
                                        url = f"https://www.instagram.com{match}"
                                    elif not match.startswith('http'):
                                        continue
                                    else:
                                        url = match
                                    if url not in post_links and 'instagram.com' in url:
                                        post_links.append(url)
                except Exception as e:
                    logger.debug(f"Ошибка в паттерне {pattern}: {e}")
                    continue
                                
        except Exception as e:
            logger.debug(f"Ошибка агрессивного парсинга: {e}")
        
        # Фильтруем только валидные ссылки
        valid_links = []
        for link in post_links:
            if '/p/' in link or '/reel/' in link or '/reels/' in link:
                # Убираем параметры из URL
                clean_link = link.split('?')[0].split('#')[0]
                if clean_link not in valid_links:
                    valid_links.append(clean_link)
        
        return valid_links
    
    def _parse_json_response(self, data: Dict[str, Any]) -> List[str]:
        """Парсинг JSON ответа от Instagram API (УЛУЧШЕННЫЙ - проверяет все поля)."""
        post_links = []
        
        try:
            # Разные структуры JSON ответов (МАКСИМАЛЬНО АГРЕССИВНЫЙ ПАРСИНГ)
            def extract_from_node(node, depth=0):
                """Рекурсивно извлекаем shortcode из узла (улучшенный)."""
                if depth > 10:  # Ограничиваем глубину рекурсии
                    return []
                    
                links = []
                if isinstance(node, dict):
                    # Проверяем все возможные поля для shortcode
                    shortcode = (
                        node.get('shortcode') or 
                        node.get('code') or 
                        node.get('id') or
                        node.get('short_code')
                    )
                    
                    # Проверяем все возможные индикаторы видео
                    is_video = (
                        node.get('is_video', False) or 
                        node.get('type') == 2 or 
                        node.get('media_type') == 'VIDEO' or
                        node.get('__typename') == 'GraphVideo' or
                        node.get('media_type') == 2 or
                        node.get('video_codec') is not None or
                        'video' in str(node.get('__typename', '')).lower() or
                        node.get('video_versions') is not None or
                        node.get('video_url') is not None
                    )
                    
                    if shortcode and is_video:
                        # Проверяем, что shortcode валидный (обычно 11 символов)
                        if len(str(shortcode)) >= 6:
                            url = f"https://www.instagram.com/p/{shortcode}/"
                            if url not in links:
                                links.append(url)
                    
                    # Также проверяем permalink напрямую
                    permalink = node.get('permalink') or node.get('url')
                    if permalink and ('/p/' in permalink or '/reel/' in permalink or '/reels/' in permalink):
                        if permalink not in links:
                            links.append(permalink)
                    
                    # Рекурсивно ищем в дочерних элементах
                    for key, value in node.items():
                        # Пропускаем очень большие значения (чтобы не зависнуть)
                        if isinstance(value, (str, bytes)) and len(str(value)) > 10000:
                            continue
                        links.extend(extract_from_node(value, depth + 1))
                        
                elif isinstance(node, list):
                    for item in node:
                        links.extend(extract_from_node(item, depth + 1))
                        
                return links
            
            # Пробуем разные структуры (ВСЕ ВОЗМОЖНЫЕ ВАРИАНТЫ)
            structures_to_check = [
                data.get('data'),
                data.get('graphql'),
                data.get('hashtag'),
                data.get('entry_data'),
                data.get('items'),
                data.get('posts'),
                data.get('media'),
                data.get('recent'),
                data.get('top_posts'),
            ]
            
            for structure in structures_to_check:
                if structure:
                    links = extract_from_node(structure)
                    post_links.extend(links)
            
            # Прямой поиск во всей структуре (если ничего не нашли)
            if not post_links:
                all_links = extract_from_node(data)
                post_links.extend(all_links)
            
        except Exception as e:
            logger.debug(f"Ошибка парсинга JSON: {e}")
        
        # Убираем дубликаты и фильтруем только валидные ссылки
        unique_links = []
        for link in set(post_links):
            if link and ('/p/' in link or '/reel/' in link or '/reels/' in link):
                # Очищаем URL от параметров
                clean_link = link.split('?')[0].split('#')[0]
                if clean_link not in unique_links:
                    unique_links.append(clean_link)
        
        return unique_links
    
    def _login_via_selenium(self) -> bool:
        """
        Умная авторизация через Selenium с защитой от блокировки.
        Использует задержки, имитацию человеческого поведения.
        
        Returns:
            True если авторизация успешна, False иначе
        """
        if self._selenium_authenticated and self._selenium_driver:
            logger.info("[OK] Selenium уже авторизован, использую существующую сессию")
            return True
        
        # Получаем список доступных аккаунтов
        accounts = []
        if settings.INSTAGRAM_USERNAME and settings.INSTAGRAM_PASSWORD:
            accounts.append((settings.INSTAGRAM_USERNAME, settings.INSTAGRAM_PASSWORD, "основной"))
        if settings.INSTAGRAM_USERNAME_2 and settings.INSTAGRAM_PASSWORD_2:
            accounts.append((settings.INSTAGRAM_USERNAME_2, settings.INSTAGRAM_PASSWORD_2, "второй"))
        
        if not accounts:
            logger.warning("[WARN] Нет логина/пароля для авторизации через Selenium")
            return False
        
        # Ротируем между аккаунтами для снижения нагрузки
        account_index = self._current_account_index % len(accounts)
        username, password, account_name = accounts[account_index]
        logger.info(f"Использую {account_name} аккаунт: {username}")
        
        # Пробуем авторизоваться с текущим аккаунтом
        success = self._try_login_with_account(username, password, account_name)
        
        # Если не получилось и есть другие аккаунты - пробуем их
        if not success and len(accounts) > 1:
            logger.warning(f"[WARN] Не удалось авторизоваться с {account_name} аккаунтом, пробую другие...")
            for idx, (other_username, other_password, other_name) in enumerate(accounts):
                if idx != account_index:
                    logger.info(f"Пробую {other_name} аккаунт: {other_username}")
                    success = self._try_login_with_account(other_username, other_password, other_name)
                    if success:
                        self._current_account_index = idx  # Обновляем индекс успешного аккаунта
                        break
        
        return success
    
    def _load_cookies_from_file(self, username: str) -> Optional[Dict]:
        """Загрузить cookies из файла для аккаунта."""
        cookies_file = self._cookies_dir / f"{username}_cookies.json"
        if cookies_file.exists():
            try:
                with open(cookies_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    logger.info(f"[OK] Загружены cookies для {username} из файла")
                    return cookies
            except Exception as e:
                logger.debug(f"Ошибка загрузки cookies: {e}")
        return None
    
    def _save_cookies_to_file(self, username: str, cookies: List[Dict]):
        """Сохранить cookies в файл для аккаунта."""
        cookies_file = self._cookies_dir / f"{username}_cookies.json"
        try:
            # Конвертируем cookies в словарь для сохранения
            cookies_dict = {}
            for cookie in cookies:
                cookies_dict[cookie.get('name')] = cookie.get('value')
            
            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies_dict, f, indent=2)
            logger.info(f"[OK] Cookies для {username} сохранены в файл")
        except Exception as e:
            logger.warning(f"[WARN] Не удалось сохранить cookies: {e}")
    
    def _try_login_with_account(self, username: str, password: str, account_name: str) -> bool:
        """
        Попытка авторизации с конкретным аккаунтом.
        Пробует методы по порядку:
        1. Undetected-ChromeDriver (приоритет)
        2. Nodriver (fallback)
        
        Args:
            username: Логин
            password: Пароль
            account_name: Название аккаунта (для логов)
        
        Returns:
            True если авторизация успешна
        """
        
        # Метод 1: Undetected-ChromeDriver (ПРИОРИТЕТ)
        logger.info(f"[МЕТОД 1] Пробую Undetected-ChromeDriver для {account_name} аккаунта...")
        success = self._try_login_undetected_chromedriver(username, password, account_name)
        if success:
            return True
        
        # Метод 2: Nodriver (FALLBACK)
        logger.warning(f"[МЕТОД 2] Undetected-ChromeDriver не сработал, пробую Nodriver для {account_name} аккаунта...")
        success = self._try_login_nodriver(username, password, account_name)
        if success:
            return True
        
        logger.error(f"[ERROR] Оба метода авторизации не сработали для {account_name} аккаунта")
        return False
    
    def _try_login_undetected_chromedriver(self, username: str, password: str, account_name: str) -> bool:
        """
        Авторизация через Undetected-ChromeDriver (МЕТОД 1).
        
        Args:
            username: Логин
            password: Пароль
            account_name: Название аккаунта
        
        Returns:
            True если успешно
        """
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import TimeoutException, NoSuchElementException
            from selenium.webdriver.common.keys import Keys
            
            logger.info(f"Инициализирую Undetected-ChromeDriver для {account_name} аккаунта...")
            
            # Сначала пробуем загрузить сохраненные cookies
            saved_cookies = self._load_cookies_from_file(username)
            
            # Настройка Undetected-ChromeDriver
            # headless: по умолчанию False — Instagram сильно детектит headless, логин надёжнее с окном. Для сервера: INSTAGRAM_HEADLESS=1 в .env
            use_headless = (settings.INSTAGRAM_HEADLESS or "0").lower() in ("1", "true", "yes", "on")
            if use_headless:
                options = uc.ChromeOptions()
                options.add_argument('--headless=new')
            else:
                options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            user_agent = self._load_user_agent()
            options.add_argument(f'--user-agent={user_agent}')
            
            user_data_dir = self._cookies_dir / f"uc_profile_{username}"
            options.add_argument(f'--user-data-dir={user_data_dir.absolute()}')
            
            try:
                driver = uc.Chrome(options=options, headless=use_headless, use_subprocess=False)
            except Exception as e:
                logger.error(f"[ERROR] Не удалось создать Undetected-ChromeDriver: {e}")
                logger.info("Проверьте установку: pip install undetected-chromedriver")
                return False
            
            try:
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(5)
                
                # Пробуем использовать сохраненные cookies
                if saved_cookies:
                    logger.info(f"Пробую использовать сохраненные cookies для {username}...")
                    try:
                        driver.get("https://www.instagram.com/")
                        time.sleep(2)
                        
                        # Загружаем cookies
                        for name, value in saved_cookies.items():
                            try:
                                driver.add_cookie({'name': name, 'value': value, 'domain': '.instagram.com'})
                            except:
                                pass
                        
                        # Проверяем авторизацию
                        driver.get("https://www.instagram.com/")
                        time.sleep(3)
                        
                        current_url = driver.current_url
                        cookies = driver.get_cookies()
                        has_sessionid = any(c.get('name') == 'sessionid' for c in cookies)
                        
                        if has_sessionid and 'login' not in current_url.lower():
                            self._selenium_driver = driver
                            self._selenium_authenticated = True
                            logger.info(f"[OK] Использованы сохраненные cookies для {username} - авторизация успешна!")
                            return True
                        else:
                            logger.warning(f"[WARN] Сохраненные cookies устарели для {username}, нужна новая авторизация")
                    except Exception as e:
                        logger.debug(f"Ошибка при использовании сохраненных cookies: {e}")
                
                # Авторизация через форму
                logger.info("Загружаю страницу логина...")
                driver.get("https://www.instagram.com/accounts/login/")
                time.sleep(5)  # Ждём полной загрузки (React)
                
                # Закрываем cookie consent: "Accept", "Allow all" (по шагам 2024–2025)
                try:
                    for e in driver.find_elements(By.XPATH, "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept') or contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'allow')]"):
                        if e.is_displayed():
                            t = (e.text or "").lower()
                            if 'accept' in t or 'allow' in t or 'разрешить' in t or 'принять' in t:
                                e.click()
                                logger.info("[OK] Закрыт cookie/consent popup")
                                time.sleep(1.5)
                                break
                except Exception:
                    pass
                
                # Явное ожидание появления формы (input name=username)
                try:
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="username"]')))
                except TimeoutException:
                    try:
                        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="text"]')))
                    except TimeoutException:
                        pass
                
                page_source = driver.page_source
                
                # Ищем поля ввода - пробуем ВСЕ возможные варианты
                username_field = None
                password_field = None
                
                # Приоритет: input внутри формы, name=username (по шагам 2024–2025)
                username_selectors = [
                    (By.CSS_SELECTOR, 'form input[name="username"]'),
                    (By.XPATH, '//form//input[@name="username"]'),
                    (By.NAME, "username"),
                    (By.CSS_SELECTOR, 'input[name="username"]'),
                    (By.CSS_SELECTOR, 'input[aria-label*="Phone number"]'),
                    (By.CSS_SELECTOR, 'input[aria-label*="Username"]'),
                    (By.CSS_SELECTOR, 'input[aria-label*="username"]'),
                    (By.CSS_SELECTOR, 'input[type="text"]'),
                    (By.CSS_SELECTOR, 'input[placeholder*="Phone number"]'),
                    (By.CSS_SELECTOR, 'input[placeholder*="Username"]'),
                    (By.CSS_SELECTOR, 'input[placeholder*="username"]'),
                    (By.XPATH, '//input[@name="username"]'),
                    (By.XPATH, '//input[contains(@aria-label, "username") or contains(@aria-label, "Username")]'),
                    (By.XPATH, '//input[@type="text" and (contains(@placeholder, "username") or contains(@placeholder, "Username"))]'),
                ]
                
                # Приоритет: input внутри формы, name=password
                password_selectors = [
                    (By.CSS_SELECTOR, 'form input[name="password"]'),
                    (By.XPATH, '//form//input[@name="password"]'),
                    (By.NAME, "password"),
                    (By.CSS_SELECTOR, 'input[name="password"]'),
                    (By.CSS_SELECTOR, 'input[type="password"]'),
                    (By.CSS_SELECTOR, 'input[aria-label*="Password"]'),
                    (By.CSS_SELECTOR, 'input[aria-label*="password"]'),
                    (By.XPATH, '//input[@name="password"]'),
                    (By.XPATH, '//input[@type="password"]'),
                    (By.XPATH, '//input[contains(@aria-label, "password") or contains(@aria-label, "Password")]'),
                ]
                
                logger.info("Ищу поля ввода (пробую все возможные селекторы)...")
                
                # Пробуем найти username поле
                for selector_type, selector_value in username_selectors:
                    try:
                        if selector_type == By.XPATH:
                            elements = driver.find_elements(By.XPATH, selector_value)
                        else:
                            elements = driver.find_elements(selector_type, selector_value)
                        
                        if elements:
                            # Берем первое видимое поле
                            for elem in elements:
                                try:
                                    if elem.is_displayed():
                                        username_field = elem
                                        logger.info(f"[OK] Найдено поле username через селектор: {selector_type}={selector_value}")
                                        break
                                except:
                                    continue
                            if username_field:
                                break
                    except Exception as e:
                        logger.debug(f"Селектор {selector_type}={selector_value} не сработал: {e}")
                        continue
                
                # Пробуем найти password поле
                for selector_type, selector_value in password_selectors:
                    try:
                        if selector_type == By.XPATH:
                            elements = driver.find_elements(By.XPATH, selector_value)
                        else:
                            elements = driver.find_elements(selector_type, selector_value)
                        
                        if elements:
                            # Берем первое видимое поле
                            for elem in elements:
                                try:
                                    if elem.is_displayed():
                                        password_field = elem
                                        logger.info(f"[OK] Найдено поле password через селектор: {selector_type}={selector_value}")
                                        break
                                except:
                                    continue
                            if password_field:
                                break
                    except Exception as e:
                        logger.debug(f"Селектор {selector_type}={selector_value} не сработал: {e}")
                        continue
                
                # Если не нашли через селекторы - пробуем через JavaScript
                if not username_field or not password_field:
                    logger.warning("Поля не найдены через селекторы, пробую через JavaScript...")
                    try:
                        # Ищем все input поля
                        all_inputs = driver.execute_script("""
                            var inputs = document.querySelectorAll('input');
                            var result = {username: null, password: null};
                            for (var i = 0; i < inputs.length; i++) {
                                var input = inputs[i];
                                var name = input.name || '';
                                var type = input.type || '';
                                var placeholder = input.placeholder || '';
                                var ariaLabel = input.getAttribute('aria-label') || '';
                                
                                if (!result.username && (name.includes('username') || type === 'text' || 
                                    placeholder.toLowerCase().includes('username') || 
                                    ariaLabel.toLowerCase().includes('username'))) {
                                    result.username = input;
                                }
                                if (!result.password && (name.includes('password') || type === 'password')) {
                                    result.password = input;
                                }
                            }
                            return result;
                        """)
                        
                        if all_inputs.get('username'):
                            username_field = driver.execute_script("return arguments[0];", all_inputs['username'])
                        if all_inputs.get('password'):
                            password_field = driver.execute_script("return arguments[0];", all_inputs['password'])
                            
                        if username_field and password_field:
                            logger.info("[OK] Поля найдены через JavaScript")
                    except Exception as e:
                        logger.debug(f"Ошибка поиска через JavaScript: {e}")
                
                # Финальная проверка
                if not username_field or not password_field:
                    logger.error(f"[ERROR] Не найдены поля ввода для {account_name} аккаунта (Undetected-ChromeDriver)")
                    logger.error(f"Текущий URL: {driver.current_url}")
                    logger.error(f"Заголовок страницы: {driver.title}")
                    
                    # Сохраняем HTML для анализа
                    debug_file = self._cookies_dir / f"debug_login_{username}.html"
                    try:
                        with open(debug_file, 'w', encoding='utf-8', errors='ignore') as f:
                            f.write(page_source)
                        logger.error(f"HTML страницы сохранен в {debug_file} для анализа")
                    except:
                        pass
                    
                    return False
                
                # Вводим логин
                logger.info(f"Ввожу логин ({account_name} аккаунт)...")
                username_field.clear()
                time.sleep(random.uniform(0.3, 0.7))
                for char in username:
                    username_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))
                time.sleep(random.uniform(0.5, 1.5))
                
                # Вводим пароль
                logger.info("Ввожу пароль...")
                password_field.clear()
                time.sleep(random.uniform(0.3, 0.7))
                for char in password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.15))
                time.sleep(random.uniform(0.5, 1.0))
                
                # Нажимаем кнопку входа
                try:
                    login_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
                    driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
                    time.sleep(random.uniform(0.3, 0.7))
                    login_button.click()
                except NoSuchElementException:
                    password_field.send_keys(Keys.RETURN)
                
                # Ждем авторизации (8–10 сек: React + редирект + cookie; по шагам 2024–2025)
                logger.info("Ожидаю авторизацию...")
                time.sleep(random.uniform(8, 10))
                
                current_url = driver.current_url
                
                if 'challenge' in current_url.lower() or 'checkpoint' in current_url.lower():
                    logger.error(f"[ERROR] Instagram требует проверку для {account_name} аккаунта")
                    return False
                
                if 'two_factor' in current_url.lower() or '2fa' in current_url.lower():
                    logger.error(f"[ERROR] Требуется двухфакторная аутентификация для {account_name} аккаунта")
                    return False
                
                # Закрываем popup "Save Your Login Info" и "Turn on Notifications" (кнопка "Not Now" / "Не сейчас")
                not_now_texts = ('not now', 'не сейчас', 'later', 'позже')
                for _ in range(2):  # До 2 popup: Save Login + Notifications
                    try:
                        btns = driver.find_elements(By.XPATH, "//button | //div[@role='button'] | //span[@role='button']/..")
                        for btn in btns:
                            try:
                                t = (btn.text or "").strip().lower()
                                if t and any(x in t for x in not_now_texts) and btn.is_displayed():
                                    btn.click()
                                    logger.info("[OK] Закрыт popup 'Not Now'")
                                    time.sleep(random.uniform(1.5, 2.5))
                                    break
                            except:
                                continue
                    except:
                        pass
                
                time.sleep(random.uniform(1, 2))
                
                # ГЛАВНОЕ: sessionid появляется в cookies сразу после успешного логина, даже при открытом popup
                cookies = driver.get_cookies()
                has_sessionid = any(c.get('name') == 'sessionid' for c in cookies)
                
                if has_sessionid:
                    self._selenium_driver = driver
                    self._selenium_authenticated = True
                    self._save_cookies_to_file(username, cookies)
                    logger.info(f"[OK] Undetected-ChromeDriver: авторизация успешна ({account_name} аккаунт: {username})!")
                    return True
                
                # Если sessionid нет - проверяем ошибки
                try:
                    error_elements = driver.find_elements(By.CSS_SELECTOR, '#slfErrorAlert, [role="alert"]')
                    if error_elements:
                        error_text = (error_elements[0].text or "").strip()
                        if error_text:
                            logger.error(f"[ERROR] Ошибка авторизации для {account_name} аккаунта: {error_text}")
                except:
                    pass
                
                if not has_sessionid:
                    logger.warning(f"[WARN] sessionid не найден в cookies для {account_name} аккаунта. URL: {current_url}")
                    # Скриншот для анализа (инструкции 2024–2025)
                    try:
                        path = self._cookies_dir / f"debug_login_fail_{username}.png"
                        driver.save_screenshot(str(path))
                        logger.warning(f"Скриншот сохранён: {path}")
                    except Exception:
                        pass
                    # Извлекаем и логируем текст ошибки со страницы
                    err_sel = ["#slfErrorAlert", "[role='alert']", "div[class*='error']", "p[class*='error']", "span[class*='error']"]
                    for sel in err_sel:
                        try:
                            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                                t = (el.text or "").strip()
                                if t and len(t) < 500:
                                    logger.warning(f"Текст с страницы ({sel}): {t}")
                                    break
                        except Exception:
                            pass
                    # Ищем по типичным фразам Instagram
                    pg = (driver.page_source or "").lower()
                    for phrase in ["sorry, your password was incorrect", "the password you entered was incorrect", "try again later", "suspicious", "try again", "incorrect password", "неверный пароль", "попробуйте снова"]:
                        if phrase in pg:
                            logger.warning(f"На странице найдена фраза: \"{phrase}\"")
                return False
                    
            except Exception as e:
                logger.error(f"[ERROR] Ошибка при авторизации через Undetected-ChromeDriver ({account_name} аккаунт): {e}")
                import traceback
                logger.debug(traceback.format_exc())
                return False
            finally:
                # НЕ закрываем драйвер если авторизация успешна
                if not self._selenium_authenticated:
                    try:
                        driver.quit()
                    except:
                        pass
                
        except ImportError:
            logger.warning("[WARN] Undetected-ChromeDriver не установлен. Установите: pip install undetected-chromedriver")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Критическая ошибка Undetected-ChromeDriver ({account_name} аккаунт): {e}")
            return False
    
    def _try_login_nodriver(self, username: str, password: str, account_name: str) -> bool:
        """
        Авторизация через Nodriver (МЕТОД 2 - FALLBACK).
        
        Args:
            username: Логин
            password: Пароль
            account_name: Название аккаунта
        
        Returns:
            True если успешно
        """
        try:
            import nodriver as uc
            import asyncio
            
            logger.info(f"Инициализирую Nodriver для {account_name} аккаунта...")
            
            async def login_async():
                try:
                    # Запускаем браузер. "Failed to connect to browser" — передать --no-sandbox через browser_args
                    browser = await uc.start(headless=True, browser_args=["--no-sandbox", "--disable-dev-shm-usage"])
                    page = await browser.get('https://www.instagram.com/accounts/login/')
                    
                    await page.sleep(random.uniform(2, 4))
                    
                    # Ищем поля ввода - пробуем все варианты
                    username_input = None
                    password_input = None
                    
                    username_selectors = [
                        'input[name="username"]',
                        'input[aria-label*="username"]',
                        'input[aria-label*="Username"]',
                        'input[type="text"]',
                        'input[placeholder*="username"]',
                        'input[placeholder*="Username"]',
                    ]
                    
                    password_selectors = [
                        'input[name="password"]',
                        'input[type="password"]',
                        'input[aria-label*="password"]',
                        'input[aria-label*="Password"]',
                    ]
                    
                    logger.info("Ищу поля ввода через Nodriver (пробую все селекторы)...")
                    
                    for selector in username_selectors:
                        try:
                            elements = await page.select_all(selector)
                            if elements:
                                for elem in elements:
                                    try:
                                        if await elem.is_visible():
                                            username_input = elem
                                            logger.info(f"[OK] Найдено поле username через селектор: {selector}")
                                            break
                                    except:
                                        continue
                                if username_input:
                                    break
                        except:
                            continue
                    
                    for selector in password_selectors:
                        try:
                            elements = await page.select_all(selector)
                            if elements:
                                for elem in elements:
                                    try:
                                        if await elem.is_visible():
                                            password_input = elem
                                            logger.info(f"[OK] Найдено поле password через селектор: {selector}")
                                            break
                                    except:
                                        continue
                                if password_input:
                                    break
                        except:
                            continue
                    
                    if not username_input or not password_input:
                        logger.error(f"[ERROR] Не найдены поля ввода для {account_name} аккаунта (Nodriver)")
                        logger.error(f"Текущий URL: {page.url}")
                        await browser.stop()
                        return False
                    
                    # Вводим логин
                    logger.info(f"Ввожу логин через Nodriver ({account_name} аккаунт)...")
                    await username_input.clear()
                    await page.sleep(random.uniform(0.3, 0.7))
                    for char in username:
                        await username_input.send_keys(char)
                        await page.sleep(random.uniform(0.05, 0.15))
                    await page.sleep(random.uniform(0.5, 1.5))
                    
                    # Вводим пароль
                    logger.info("Ввожу пароль через Nodriver...")
                    await password_input.clear()
                    await page.sleep(random.uniform(0.3, 0.7))
                    for char in password:
                        await password_input.send_keys(char)
                        await page.sleep(random.uniform(0.05, 0.15))
                    await page.sleep(random.uniform(0.5, 1.0))
                    
                    # Нажимаем кнопку входа
                    try:
                        login_button = await page.select('button[type="submit"]')
                        await login_button.click()
                    except:
                        await password_input.send_keys(uc.Keys.ENTER)
                    
                    # Ждем авторизации
                    logger.info("Ожидаю авторизацию через Nodriver...")
                    await page.sleep(random.uniform(4, 6))
                    
                    current_url = page.url
                    
                    if 'challenge' in current_url.lower() or 'checkpoint' in current_url.lower():
                        logger.error(f"[ERROR] Instagram требует проверку для {account_name} аккаунта (Nodriver)")
                        await browser.stop()
                        return False
                    
                    if 'two_factor' in current_url.lower() or '2fa' in current_url.lower():
                        logger.error(f"[ERROR] Требуется двухфакторная аутентификация для {account_name} аккаунта (Nodriver)")
                        await browser.stop()
                        return False
                    
                    # Закрываем popup "Not Now" / "Не сейчас" (1–2 раза)
                    not_now_texts = ('not now', 'не сейчас', 'later', 'позже')
                    for _ in range(2):
                        try:
                            btns = await page.select_all('button, [role="button"]')
                            for btn in btns:
                                try:
                                    t = (await btn.text or "").strip().lower()
                                    if t and any(x in t for x in not_now_texts) and await btn.is_visible():
                                        await btn.click()
                                        logger.info("[OK] Nodriver: закрыт popup 'Not Now'")
                                        await page.sleep(random.uniform(1.5, 2.5))
                                        break
                                except:
                                    continue
                        except:
                            pass
                    
                    await page.sleep(random.uniform(1, 2))
                    
                    # Проверяем sessionid в cookies (появляется сразу после успешного логина, даже при popup)
                    cookies = []
                    try:
                        if hasattr(browser, 'cookies'):
                            cookies = await browser.cookies.get_all() if hasattr(browser.cookies, 'get_all') else []
                        if not cookies and hasattr(page, 'cookies'):
                            cookies = await page.cookies() if callable(getattr(page, 'cookies', None)) else []
                    except Exception:
                        pass
                    if not isinstance(cookies, list):
                        cookies = list(cookies) if cookies else []
                    has_sessionid = any((c.get('name') if isinstance(c, dict) else getattr(c, 'name', '')) == 'sessionid' for c in cookies)
                    
                    if has_sessionid:
                        cookie_list = [{'name': c.get('name', getattr(c, 'name', '')), 'value': c.get('value', getattr(c, 'value', ''))} for c in cookies]
                        self._save_cookies_to_file(username, cookie_list)
                        logger.info(f"[OK] Nodriver: авторизация успешна ({account_name} аккаунт: {username})!")
                        return True
                    
                    logger.warning(f"[WARN] sessionid не найден для {account_name} аккаунта (Nodriver). URL: {current_url}")
                    await browser.stop()
                    return False
                        
                except Exception as e:
                    logger.error(f"[ERROR] Ошибка при авторизации через Nodriver ({account_name} аккаунт): {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    return False
            
            # Запускаем асинхронную функцию
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(login_async())
            loop.close()
            
            if success:
                self._selenium_authenticated = True
            
            return success
                
        except ImportError:
            logger.warning("[WARN] Nodriver не установлен. Установите: pip install nodriver")
            return False
        except Exception as e:
            logger.error(f"[ERROR] Критическая ошибка Nodriver ({account_name} аккаунт): {e}")
            return False
    
    def _close_selenium_driver(self):
        """Закрыть Selenium драйвер и очистить сессию."""
        if self._selenium_driver:
            try:
                self._selenium_driver.quit()
                logger.debug("Selenium драйвер закрыт")
            except Exception as e:
                logger.debug(f"Ошибка при закрытии драйвера: {e}")
            finally:
                self._selenium_driver = None
                self._selenium_authenticated = False
    
    def _get_hashtag_posts_via_selenium(self, hashtag: str, limit: int = 10) -> List[str]:
        """
        Получить посты по хэштегу через Selenium (рендеринг JavaScript).
        
        Args:
            hashtag: Хэштег без #
            limit: Количество постов
        
        Returns:
            Список URL постов
        """
        post_links = []
        start_time = time.time()
        max_time = 60  # Увеличено до 60 секунд для скроллинга
        
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.common.exceptions import TimeoutException, WebDriverException
            from selenium.webdriver.common.keys import Keys
            from webdriver_manager.chrome import ChromeDriverManager
            
            logger.info(f"Использую Selenium для #{hashtag}...")
            
            # Авторизуемся через Selenium (если еще не авторизованы)
            if not self._selenium_authenticated:
                if not self._login_via_selenium():
                    logger.warning("[WARN] Не удалось авторизоваться через Selenium, пробую без авторизации...")
                    # Продолжаем без авторизации - может сработает для публичных хэштегов
            
            # Используем существующий драйвер или создаем новый
            driver = self._selenium_driver
            if not driver:
                # Создаем новый драйвер только если нет авторизованного
                logger.info("Создаю новый Selenium драйвер...")
                chrome_options = Options()
                chrome_options.add_argument('--headless=new')  # Headless для сбора данных
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                user_agent = self._load_user_agent()
                chrome_options.add_argument(f'--user-agent={user_agent}')
                
                try:
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                    # Копируем cookies из авторизованного драйвера
                    if self._selenium_authenticated and self._selenium_driver:
                        for cookie in self._selenium_driver.get_cookies():
                            try:
                                driver.add_cookie(cookie)
                            except:
                                pass
                except Exception as e:
                    logger.error(f"Ошибка создания Chrome driver: {e}")
                    return post_links
            
            if not driver:
                return post_links
            
            # Флаг для закрытия драйвера в конце (только если мы его создали)
            should_close_driver = (driver != self._selenium_driver)
            
            try:
                # Устанавливаем таймауты
                driver.set_page_load_timeout(25)  # Увеличено до 25 секунд
                driver.implicitly_wait(5)  # Увеличено до 5 секунд
                
                # Проверяем общий таймаут
                if time.time() - start_time > max_time:
                    logger.warning("Превышен общий таймаут, прерываю...")
                    return post_links
                
                # Загружаем страницу хэштега с обработкой таймаута
                hashtag_url = f"https://www.instagram.com/explore/tags/{hashtag}/"
                logger.info(f"Загружаю страницу: {hashtag_url}")
                
                try:
                    driver.get(hashtag_url)
                except TimeoutException:
                    logger.warning("Таймаут загрузки страницы, пробую извлечь что есть...")
                    # Продолжаем - может быть частично загрузилось
                except Exception as e:
                    logger.warning(f"Ошибка загрузки страницы: {e}")
                    return post_links
                
                # Проверяем редирект на login СРАЗУ
                current_url = driver.current_url
                if 'login' in current_url.lower() or 'accounts/login' in current_url.lower():
                    logger.warning("Редирект на login, пропускаю...")
                    return post_links
                
                # Ждем загрузки контента
                wait_time = min(15, max_time - (time.time() - start_time))  # Увеличено до 15 секунд
                if wait_time > 0:
                    try:
                        # Ждем появления ссылок на посты
                        WebDriverWait(driver, wait_time).until(
                            lambda d: '/p/' in d.page_source or '/reel/' in d.page_source or '/reels/' in d.page_source or 'window._sharedData' in d.page_source
                        )
                        logger.info("Контент загружен, начинаю скроллинг...")
                    except TimeoutException:
                        logger.warning("Таймаут ожидания контента, пробую извлечь что есть...")
                        # Проверяем еще раз на login
                        if 'login' in driver.current_url.lower():
                            logger.warning("Редирект на login, пропускаю...")
                            return post_links
                else:
                    logger.warning("Недостаточно времени для ожидания контента")
                
                # Задержка для полной загрузки
                time.sleep(2)
                
                # Скроллинг для загрузки больше постов
                logger.info("Выполняю скроллинг для загрузки больше постов...")
                scroll_pause_time = 1
                last_height = driver.execute_script("return document.body.scrollHeight")
                scroll_count = 0
                max_scrolls = 5  # Максимум 5 скроллов
                
                while scroll_count < max_scrolls:
                    # Скроллим вниз
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(scroll_pause_time)
                    
                    # Проверяем новый контент
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                    scroll_count += 1
                    
                    # Проверяем таймаут
                    if time.time() - start_time > max_time - 10:
                        logger.warning("Приближается таймаут, прекращаю скроллинг...")
                        break
                
                logger.info(f"Выполнено {scroll_count} скроллов, извлекаю ссылки...")
                
                # Извлекаем HTML после рендеринга JavaScript и скроллинга
                page_source = driver.page_source
                
                # Парсим HTML (используем оба метода парсинга)
                html_links = self._parse_html_for_links(page_source)
                aggressive_links = self._parse_html_aggressive(page_source)
                
                # Объединяем результаты
                all_links = list(set(html_links + aggressive_links))
                
                if all_links:
                    logger.info(f"[OK] Selenium: найдено {len(all_links)} ссылок для #{hashtag}")
                    post_links.extend(all_links[:limit])
                else:
                    logger.warning(f"[WARN] Selenium не нашел ссылки для #{hashtag}")
                    # Диагностика
                    if 'window._sharedData' in page_source:
                        logger.debug("[OK] window._sharedData найден в HTML")
                    if '/p/' in page_source or '/reel/' in page_source or '/reels/' in page_source:
                        logger.debug("[WARN] Ссылки /p/ или /reel/ найдены в HTML, но парсер их не извлек")
                    
            except Exception as e:
                logger.error(f"Ошибка в Selenium для #{hashtag}: {e}")
            finally:
                # Закрываем браузер только если мы его создали (не авторизованный)
                if should_close_driver and driver:
                    try:
                        driver.quit()
                        logger.debug("Временный браузер закрыт")
                    except Exception as e:
                        logger.debug(f"Ошибка при закрытии браузера: {e}")
                        try:
                            driver.service.process.kill()
                        except:
                            pass
                    
        except ImportError:
            logger.warning("Selenium не установлен. Установите: pip install selenium webdriver-manager")
        except Exception as e:
            logger.error(f"Ошибка Selenium для #{hashtag}: {e}")
            # Убеждаемся, что браузер закрыт даже при ошибке
            try:
                if 'driver' in locals() and driver:
                    driver.quit()
            except:
                pass
        
        return post_links
    
    def find_videos_by_hashtags(self, limit_per_hashtag: int = 5) -> List[str]:
        """
        Найти видео по хэштегам темы БЕЗ авторизации (публичный парсинг).
        
        Args:
            limit_per_hashtag: Сколько видео искать по каждому хэштегу
        
        Returns:
            Список URL видео
        """
        all_video_urls = []
        
        logger.info(f"Ищу видео по хэштегам темы '{self.THEME_NAME}'...")
        logger.info(f"Хэштеги: {', '.join(['#' + h for h in self.HASHTAGS])}")
        
        try:
            import requests
            
            # Создаем сессию
            session = requests.Session()
            
            # Авторизация - ПРИОРИТЕТ: Cookies из браузера (обходит блокировку!)
            username = settings.INSTAGRAM_USERNAME
            password = settings.INSTAGRAM_PASSWORD
            
            logged_in = False
            
            # ШАГ 1: Пробуем загрузить cookies из браузера (ОБХОДИТ БЛОКИРОВКУ!)
            logger.info("="*70)
            logger.info("ПОПЫТКА ЗАГРУЗИТЬ COOKIES ИЗ БРАУЗЕРА (обход блокировки Instagram)")
            logger.info("="*70)
            
            # Пробуем Яндекс браузер ПЕРВЫМ (как просил пользователь)
            browsers_to_try = ['yandex', 'chrome', 'firefox', 'edge']
            for browser in browsers_to_try:
                logger.info(f"Пробую загрузить cookies из {browser}...")
                if load_cookies_from_browser(session, browser=browser):
                    # Проверяем работоспособность
                    test_username = test_session(session)
                    if test_username:
                        logger.info("="*70)
                        logger.info(f"[OK] Cookies из {browser} загружены и работают!")
                        logger.info(f"[OK] Пользователь: {test_username}")
                        logger.info("="*70)
                        logged_in = True
                        break
                    else:
                        logger.warning(f"[WARN] Cookies из {browser} загружены, но сессия не работает")
                else:
                    logger.debug(f"Cookies из {browser} не найдены или не загружены")
            
            # ШАГ 2: Если cookies из браузера не сработали, пробуем instaloader сессию
            if not logged_in and username:
                logger.info("Пробую загрузить сессию из instaloader...")
                if load_cookies_from_instaloader_session(session, username):
                    test_username = test_session(session)
                    if test_username:
                        logger.info(f"[OK] Сессия instaloader загружена! Пользователь: {test_username}")
                        logged_in = True
            
            # ШАГ 3: Если ничего не сработало, пробуем логин через requests (может быть заблокирован)
            if not logged_in and username and password:
                logger.info("="*70)
                logger.info("ПОПЫТКА АВТОРИЗАЦИИ ЧЕРЕЗ REQUESTS (может быть заблокирована Instagram)")
                logger.info("="*70)
                logger.warning("[WARN] Instagram часто блокирует логин с нового браузера!")
                logger.warning("[WARN] Рекомендуется использовать cookies из браузера (см. выше)")
                logged_in = self._login_to_instagram(session, username, password)
                if logged_in:
                    logger.info("="*70)
                    logger.info("[OK] Авторизация успешна! Буду использовать авторизованную сессию")
                    logger.info("="*70)
                    
                    # ПРОВЕРЯЕМ cookies ПОСЛЕ авторизации
                    logger.info(f"[DEBUG] Проверка cookies после авторизации:")
                    logger.info(f"   - ID сессии: {id(session)}")
                    logger.info(f"   - Все cookies: {list(session.cookies.keys())}")
                    logger.info(f"   - Количество cookies: {len(session.cookies)}")
                    
                    if 'sessionid' in session.cookies:
                        logger.info(f"   [OK] sessionid найден: {session.cookies.get('sessionid')[:30]}...")
                    else:
                        logger.error("   [ERROR] sessionid НЕ найден после авторизации!")
                        logger.error("   Это может означать, что авторизация не прошла полностью")
                    
                    if 'csrftoken' in session.cookies:
                        logger.info(f"   [OK] csrftoken найден: {session.cookies.get('csrftoken')[:20]}...")
                    else:
                        logger.warning("   [WARN] csrftoken не найден")
                    
                    logger.info("="*70)
                else:
                    logger.warning("[WARN] Авторизация не удалась, пробую без авторизации...")
            else:
                logger.warning("Логин/пароль не указаны в .env, работаю без авторизации")
            
            # Собираем ссылки по хэштегам
            user_agent = self._load_user_agent()
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.instagram.com/',
                'Origin': 'https://www.instagram.com',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
            }
            
            for hashtag in self.HASHTAGS:
                try:
                    logger.info(f"\n{'='*50}")
                    logger.info(f"Обрабатываю хэштег: #{hashtag}")
                    logger.info(f"{'='*50}")
                    
                    # Метод 0: Используем Instagram Graph API (ОФИЦИАЛЬНЫЙ МЕТОД - САМЫЙ ПРИОРИТЕТ!)
                    if settings.INSTAGRAM_GRAPH_API_TOKEN and settings.INSTAGRAM_GRAPH_API_USER_ID:
                        try:
                            logger.info(f"Использую Instagram Graph API для #{hashtag} (официальный метод)...")
                            graph_api_links = self._get_hashtag_posts_via_graph_api(hashtag, limit_per_hashtag * 5)
                            if graph_api_links:
                                logger.info(f"[OK] Graph API: найдено {len(graph_api_links)} ссылок для #{hashtag}")
                                all_video_urls.extend(graph_api_links)
                                logger.info(f"Всего ссылок собрано: {len(all_video_urls)}")
                                # Если нашли достаточно через Graph API, пропускаем остальные методы
                                if len(graph_api_links) >= limit_per_hashtag:
                                    logger.info(f"Найдено достаточно ссылок через Graph API ({len(graph_api_links)} >= {limit_per_hashtag}), пропускаю остальные методы")
                                    time.sleep(random.uniform(1, 2))
                                    continue
                            else:
                                logger.warning(f"[WARN] Graph API не нашел ссылки для #{hashtag}, пробую другие методы...")
                        except Exception as e:
                            logger.error(f"[ERROR] Ошибка Graph API для #{hashtag}: {e}")
                            logger.warning("Пробую другие методы...")
                    
                    # Метод 1: Используем Selenium для рендеринга JavaScript
                    try:
                        logger.info(f"Использую Selenium для #{hashtag} (рендеринг JavaScript)...")
                        selenium_links = self._get_hashtag_posts_via_selenium(hashtag, limit_per_hashtag * 5)
                        if selenium_links:
                            logger.info(f"[OK] Selenium: найдено {len(selenium_links)} ссылок для #{hashtag}")
                            all_video_urls.extend(selenium_links)
                            logger.info(f"Всего ссылок собрано: {len(all_video_urls)}")
                            # Если нашли достаточно через Selenium, пропускаем остальные методы
                            if len(selenium_links) >= limit_per_hashtag:
                                logger.info(f"Найдено достаточно ссылок через Selenium ({len(selenium_links)} >= {limit_per_hashtag}), пропускаю остальные методы")
                                time.sleep(random.uniform(2, 4))
                                continue
                        else:
                            logger.warning(f"[WARN] Selenium не нашел ссылки для #{hashtag}, пробую другие методы...")
                    except Exception as e:
                        logger.error(f"[ERROR] Ошибка Selenium для #{hashtag}: {e}")
                        logger.warning("Пробую другие методы...")
                    
                    # Метод 2: Используем INSTALOADER (если Selenium не сработал)
                    if INSTALOADER_AVAILABLE:
                        logger.info(f"Использую INSTALOADER для #{hashtag} (приоритетный метод)...")
                        try:
                            instaloader_links = self._get_hashtag_posts_via_instaloader(hashtag, limit_per_hashtag * 5)
                            if instaloader_links:
                                logger.info(f"[OK] INSTALOADER: найдено {len(instaloader_links)} ссылок для #{hashtag}")
                                all_video_urls.extend(instaloader_links)
                                logger.info(f"Всего ссылок собрано: {len(all_video_urls)}")
                                # Если нашли достаточно через instaloader, пропускаем остальные методы
                                if len(instaloader_links) >= limit_per_hashtag:
                                    logger.info(f"Найдено достаточно ссылок через INSTALOADER ({len(instaloader_links)} >= {limit_per_hashtag}), пропускаю остальные методы")
                                    time.sleep(random.uniform(2, 4))
                                    continue
                            else:
                                logger.warning(f"[WARN] INSTALOADER не нашел ссылки для #{hashtag}, пробую другие методы...")
                        except Exception as e:
                            logger.error(f"[ERROR] Ошибка INSTALOADER для #{hashtag}: {e}")
                            logger.warning("Пробую другие методы...")
                    
                    # Метод 1: Используем GraphQL API через авторизованную сессию
                    logger.info(f"Использую GraphQL API для #{hashtag}...")
                    api_links = self._get_hashtag_posts_via_api(session, hashtag, limit_per_hashtag * 10)
                    if api_links:
                        logger.info(f"[OK] GraphQL API: найдено {len(api_links)} ссылок для #{hashtag}")
                        all_video_urls.extend(api_links)
                        logger.info(f"Всего ссылок собрано: {len(all_video_urls)}")
                        # Если нашли достаточно через GraphQL API, пропускаем остальные методы
                        if len(api_links) >= limit_per_hashtag:
                            logger.info(f"Найдено достаточно ссылок через GraphQL API ({len(api_links)} >= {limit_per_hashtag}), пропускаю остальные методы")
                            time.sleep(random.uniform(2, 4))
                            continue
                    else:
                        logger.warning(f"[WARN] GraphQL API не нашел ссылки для #{hashtag}, пробую другие методы...")
                    
                    # Метод 1.5: Пробуем GraphQL с разными query_hash (если основной не сработал)
                    graphql_query_hashes = [
                        "9b498c08113f1e09617a1703c22b2f32",  # Основной
                        "f92f56e47e7a818121d18262dce6ec2a",  # Альтернативный 1
                        "174a25488b2c2dd3beda9c03f5093488",  # Альтернативный 2
                    ]
                    
                    for query_hash in graphql_query_hashes:
                        try:
                            graphql_query = {
                                "query_hash": query_hash,
                                "variables": json.dumps({
                                    "tag_name": hashtag,
                                    "first": 50,  # Увеличиваем лимит
                                    "after": None
                                })
                            }
                            
                            graphql_url = "https://www.instagram.com/graphql/query/"
                            graphql_headers = headers.copy()
                            graphql_headers['Accept'] = '*/*'
                            graphql_headers['X-Requested-With'] = 'XMLHttpRequest'
                            graphql_headers['X-IG-App-ID'] = '936619743392459'
                            graphql_headers['X-Instagram-AJAX'] = '1'
                            
                            if 'csrftoken' in session.cookies:
                                graphql_headers['X-CSRFToken'] = session.cookies['csrftoken']
                            
                            logger.debug(f"Пробую GraphQL с query_hash {query_hash[:10]}... для #{hashtag}")
                            graphql_response = session.get(
                                graphql_url,
                                params=graphql_query,
                                headers=graphql_headers,
                                timeout=15
                            )
                            if graphql_response.status_code == 200:
                                try:
                                    data = graphql_response.json()
                                    
                                    # Сохраняем JSON для отладки (только первый хэштег и первый query_hash)
                                    if hashtag == self.HASHTAGS[0] and query_hash == graphql_query_hashes[0]:
                                        debug_graphql_file = Path("debug_html") / f"instagram_{hashtag}_graphql.json"
                                        debug_graphql_file.parent.mkdir(exist_ok=True)
                                        try:
                                            with open(debug_graphql_file, 'w', encoding='utf-8') as f:
                                                json.dump(data, f, indent=2, ensure_ascii=False)
                                            logger.info(f"GraphQL JSON сохранен в {debug_graphql_file} для анализа")
                                        except:
                                            pass
                                    
                                    json_links = self._parse_json_response(data)
                                    if json_links:
                                        logger.info(f"[OK] GraphQL (hash {query_hash[:10]}...): найдено {len(json_links)} ссылок для #{hashtag}")
                                        all_video_urls.extend(json_links)
                                        # Если нашли достаточно, пропускаем остальные query_hash
                                        if len(json_links) >= limit_per_hashtag:
                                            break
                                except json.JSONDecodeError:
                                    logger.debug(f"GraphQL ответ не JSON для hash {query_hash[:10]}...")
                        except Exception as e:
                            logger.debug(f"Ошибка GraphQL с hash {query_hash[:10]}...: {e}")
                            continue
                    
                    # Если нашли через GraphQL, пропускаем остальные методы
                    if len([url for url in all_video_urls if hashtag in url or True]) >= limit_per_hashtag:
                        time.sleep(random.uniform(2, 4))
                        continue
                    
                    # Метод 2: Пробуем дополнительные JSON endpoints (если GraphQL API не нашел достаточно)
                    json_endpoints = [
                        f"https://www.instagram.com/api/v1/tags/web_info/?tag_name={hashtag}",
                        f"https://www.instagram.com/explore/tags/{hashtag}/?__a=1&__d=dis",
                    ]
                    
                    for json_url in json_endpoints:
                        try:
                            logger.debug(f"Пробую дополнительный JSON endpoint: {json_url}")
                            json_headers = headers.copy()
                            json_headers['Accept'] = 'application/json'
                            json_headers['X-Requested-With'] = 'XMLHttpRequest'
                            json_headers['X-IG-App-ID'] = '936619743392459'
                            
                            if 'csrftoken' in session.cookies:
                                json_headers['X-CSRFToken'] = session.cookies['csrftoken']
                            
                            json_response = session.get(json_url, headers=json_headers, timeout=15)
                            if json_response.status_code == 200:
                                try:
                                    data = json_response.json()
                                    # Парсим JSON ответ
                                    json_links = self._parse_json_response(data)
                                    if json_links:
                                        logger.info(f"[OK] JSON endpoint: найдено {len(json_links)} ссылок для #{hashtag}")
                                        all_video_urls.extend(json_links)
                                        break  # Если нашли через JSON, пропускаем HTML парсинг
                                except json.JSONDecodeError:
                                    logger.debug("Ответ не JSON")
                        except Exception as e:
                            logger.debug(f"Ошибка JSON endpoint {json_url}: {e}")
                            continue
                    
                    # Метод 2: Парсим десктопную HTML страницу
                    from urllib.parse import quote
                    hashtag_encoded = quote(hashtag)
                    hashtag_url = f"https://www.instagram.com/explore/tags/{hashtag_encoded}/"
                    logger.info(f"Загружаю десктопную версию: {hashtag_url}")
                    
                    try:
                        response = session.get(hashtag_url, headers=headers, timeout=20, allow_redirects=True)
                        
                        # Проверяем, что ответ распакован правильно
                        html_content = response.text
                        
                        # Если контент выглядит как бинарный, пробуем распаковать вручную
                        if not html_content or len(html_content) < 1000 or html_content.startswith('\x1f\x8b'):
                            try:
                                import gzip
                                if response.content.startswith(b'\x1f\x8b'):
                                    logger.debug("Контент сжат gzip, распаковываю...")
                                    html_content = gzip.decompress(response.content).decode('utf-8', errors='ignore')
                                else:
                                    html_content = response.content.decode('utf-8', errors='ignore')
                            except:
                                html_content = response.content.decode('utf-8', errors='ignore')
                        
                        logger.info(f"Статус: {response.status_code}, размер HTML: {len(html_content)} символов, URL: {response.url}")
                        
                        # Проверяем, не редирект ли на login
                        if 'login' in response.url.lower() or 'accounts/login' in response.url.lower():
                            logger.warning(f"[WARN] #{hashtag} редиректит на login - пробую популярные посты...")
                            # Пробуем популярные посты (иногда доступны без авторизации)
                            from urllib.parse import quote
                            hashtag_encoded = quote(hashtag)
                            popular_url = f"https://www.instagram.com/popular/{hashtag_encoded}/"
                            try:
                                popular_response = session.get(popular_url, headers=headers, timeout=15)
                                if popular_response.status_code == 200 and len(popular_response.text) > 1000:
                                    html_content = popular_response.text
                                    logger.info(f"[OK] Загрузил популярные посты для #{hashtag}")
                            except:
                                pass
                            
                            # Если все равно редирект, пробуем парсить то что есть
                            if 'login' in response.url.lower():
                                logger.warning(f"[WARN] Пропускаю #{hashtag} - требует авторизации")
                                continue
                        
                        if response.status_code == 200 and len(html_content) > 1000:
                            # Сохраняем HTML для отладки (только первый хэштег)
                            if hashtag == self.HASHTAGS[0]:
                                debug_file = Path("debug_html") / f"instagram_{hashtag}.html"
                                debug_file.parent.mkdir(exist_ok=True)
                                try:
                                    with open(debug_file, 'w', encoding='utf-8', errors='ignore') as f:
                                        f.write(html_content)
                                    logger.info(f"HTML сохранен в {debug_file} для анализа")
                                except Exception as e:
                                    logger.debug(f"Не удалось сохранить HTML: {e}")
                            
                            # Парсим HTML (ОБЯЗАТЕЛЬНО пробуем оба метода)
                            html_links = self._parse_html_for_links(html_content)
                            
                            # ВСЕГДА пробуем агрессивный парсинг тоже
                            aggressive_links = self._parse_html_aggressive(html_content)
                            if aggressive_links:
                                html_links.extend(aggressive_links)
                            
                            # Убираем дубликаты
                            html_links = list(set(html_links))
                            
                            if html_links:
                                logger.info(f"[OK] HTML парсинг: найдено {len(html_links)} ссылок для #{hashtag}")
                                all_video_urls.extend(html_links)
                            else:
                                logger.warning(f"[WARN] HTML парсинг не нашел ссылки для #{hashtag}")
                                # Дополнительная диагностика
                                if 'window._sharedData' in html_content:
                                    logger.debug("[OK] window._sharedData найден в HTML")
                                else:
                                    logger.debug("[WARN] window._sharedData НЕ найден в HTML")
                                
                                if '/p/' in html_content or '/reel/' in html_content or '/reels/' in html_content:
                                    logger.debug("[OK] Ссылки /p/ или /reel/ найдены в HTML, но парсер их не извлек")
                                    # Показываем примеры найденных упоминаний
                                    p_matches = re.findall(r'/p/([\w-]+)', html_content)
                                    reel_matches = re.findall(r'/reels?/([\w-]+)', html_content)
                                    logger.debug(f"Найдено упоминаний /p/: {len(p_matches)}, /reel/: {len(reel_matches)}")
                                    if p_matches:
                                        logger.debug(f"Примеры shortcode: {p_matches[:5]}")
                                else:
                                    logger.warning(f"[WARN] В HTML нет упоминаний /p/ или /reel/")
                        else:
                            logger.warning(f"[WARN] Пропуск #{hashtag}: статус {response.status_code} или HTML слишком короткий ({len(html_content)} символов)")
                    except Exception as e:
                        logger.error(f"Ошибка при загрузке #{hashtag}: {e}")
                        continue
                    
                    # Задержка между запросами
                    delay = random.uniform(3, 6)
                    logger.info(f"Задержка {delay:.1f} сек перед следующим хэштегом...")
                    time.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Ошибка обработки #{hashtag}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Ошибка сбора ссылок: {e}")
        
        # Убираем дубликаты
        unique_urls = list(set(all_video_urls))
        logger.info(f"\n{'='*70}")
        logger.info(f"[OK] Всего найдено уникальных видео: {len(unique_urls)}")
        logger.info(f"{'='*70}")
        
        # Сохраняем ссылки в файл
        if unique_urls:
            links_file = Path("instagram_links") / f"humor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            links_file.parent.mkdir(exist_ok=True)
            with open(links_file, 'w', encoding='utf-8') as f:
                for url in unique_urls:
                    f.write(f"{url}\n")
            logger.info(f"[OK] Ссылки сохранены в файл: {links_file}")
        
        return unique_urls
    
    def save_to_database(self, video_url: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[Video]:
        """
        Сохранить информацию о видео в БД.
        
        Args:
            video_url: URL видео
            metadata: Дополнительные метаданные
        
        Returns:
            Объект Video из БД или None
        """
        try:
            shortcode = extract_shortcode(video_url)
            if not shortcode:
                logger.warning(f"Не удалось извлечь shortcode из {video_url}")
                return None
            
            # Проверяем, не существует ли уже такое видео
            existing = self.db.query(Video).filter(
                Video.source_post_id == shortcode,
                Video.topic_id == self.topic.id
            ).first()
            
            if existing:
                logger.debug(f"Видео {shortcode} уже существует в БД")
                return existing
            
            # Создаем запись в БД
            video = Video(
                topic_id=self.topic.id,
                status=VideoStatus.FOUND,
                source_url=video_url,
                source_platform="instagram",
                source_post_id=shortcode,
                source_author=metadata.get("author") if metadata else None,
                title=metadata.get("title") if metadata else None,
                description=metadata.get("description") if metadata else None,
                tags=metadata.get("tags", []) if metadata else [],
                duration=metadata.get("duration") if metadata else None,
                metadata_json=metadata or {}
            )
            
            self.db.add(video)
            self.db.commit()
            self.db.refresh(video)
            
            logger.info(f"Видео {shortcode} сохранено в БД (ID: {video.id})")
            return video
            
        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}")
            self.db.rollback()
            return None
    
    def download_video(self, video_url: str, video_db: Video) -> bool:
        """
        Скачать видео и обновить путь в БД.
        
        Args:
            video_url: URL видео
            video_db: Объект Video из БД
        
        Returns:
            True если успешно
        """
        try:
            shortcode = extract_shortcode(video_url) or f"video_{video_db.id}"
            output_path = self.theme_folder / f"{shortcode}.mp4"
            
            # Используем протестированный метод скачивания
            success = download_video_combined(video_url, str(output_path))
            
            if success and output_path.exists():
                # Обновляем БД
                video_db.original_file_path = str(output_path)
                video_db.status = VideoStatus.DOWNLOADED
                video_db.downloaded_at = datetime.utcnow()
                self.db.commit()
                
                logger.info(f"Видео скачано: {output_path}")
                return True
            else:
                video_db.status = VideoStatus.ERROR
                video_db.error_message = "Не удалось скачать видео"
                self.db.commit()
                return False
                
        except Exception as e:
            logger.error(f"Ошибка скачивания видео: {e}")
            if video_db:
                video_db.status = VideoStatus.ERROR
                video_db.error_message = str(e)
                self.db.commit()
            return False
    
    def collect_and_download(self, limit: int = 10, download: bool = True) -> Dict[str, Any]:
        """
        Найти видео, сохранить в БД и скачать.
        
        Args:
            limit: Максимальное количество видео
            download: Скачивать ли видео сразу
        
        Returns:
            Статистика сбора
        """
        logger.info(f"Начинаю сбор видео для темы '{self.THEME_NAME}'...")
        
        # Ищем видео по хэштегам (увеличиваем лимит для поиска большего количества)
        # Ищем минимум по 10-15 видео на хэштег, чтобы было из чего выбрать
        limit_per_hashtag = max(10, limit // len(self.HASHTAGS) + 5)
        logger.info(f"Ищу по {limit_per_hashtag} видео на каждый хэштег...")
        video_urls = self.find_videos_by_hashtags(limit_per_hashtag=limit_per_hashtag)
        video_urls = video_urls[:limit]  # Ограничиваем общее количество для обработки
        
        saved_count = 0
        downloaded_count = 0
        failed_count = 0
        
        for i, video_url in enumerate(video_urls, 1):
            logger.info(f"\n[{i}/{len(video_urls)}] Обрабатываю: {video_url}")
            
            # Сохраняем в БД
            video_db = self.save_to_database(video_url)
            
            if not video_db:
                failed_count += 1
                continue
            
            saved_count += 1
            
            # Скачиваем если нужно
            if download:
                if self.download_video(video_url, video_db):
                    downloaded_count += 1
                else:
                    failed_count += 1
        
        result = {
            'found': len(video_urls),
            'saved_to_db': saved_count,
            'downloaded': downloaded_count,
            'failed': failed_count,
            'theme': self.THEME_NAME
        }
        
        logger.info(f"\n{'='*70}")
        logger.info(f"СБОР ЗАВЕРШЕН для темы '{self.THEME_NAME}'")
        logger.info(f"Найдено: {result['found']}")
        logger.info(f"Сохранено в БД: {result['saved_to_db']}")
        logger.info(f"Скачано: {result['downloaded']}")
        logger.info(f"Ошибок: {result['failed']}")
        logger.info(f"{'='*70}")
        
        # Закрываем Selenium драйвер в конце работы
        self._close_selenium_driver()
        
        return result
