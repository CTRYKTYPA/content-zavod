"""
Модуль для работы с Instagram Graph API.

Предоставляет методы для:
- Поиска хэштегов
- Получения постов по хэштегам
- Обмена токенов
- Проверки валидности токенов
"""
import time
from typing import List, Optional, Dict, Any
from loguru import logger
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings


class InstagramGraphAPI:
    """Класс для работы с Instagram Graph API."""
    
    BASE_URL = "https://graph.instagram.com"
    FACEBOOK_BASE_URL = "https://graph.facebook.com"
    API_VERSION = "v24.0"  # Актуальная версия на 2026 год
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None
    ):
        """
        Инициализация Instagram Graph API клиента.
        
        Args:
            access_token: Access token для API (если None, берется из settings)
            user_id: Instagram User ID (если None, берется из settings)
            app_id: App ID (если None, берется из settings)
            app_secret: App Secret (если None, берется из settings)
        """
        self.access_token = access_token or settings.INSTAGRAM_GRAPH_API_TOKEN
        self.user_id = user_id or settings.INSTAGRAM_GRAPH_API_USER_ID
        self.app_id = app_id or settings.INSTAGRAM_GRAPH_API_APP_ID
        self.app_secret = app_secret or settings.INSTAGRAM_GRAPH_API_APP_SECRET
        
        # Создаем сессию с retry логикой
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
    
    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        use_facebook_api: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Выполнить запрос к Instagram Graph API или Facebook Graph API.
        
        Args:
            endpoint: Endpoint API (например, 'ig_hashtag_search')
            method: HTTP метод ('GET' или 'POST')
            params: Параметры запроса
            timeout: Таймаут запроса в секундах
            use_facebook_api: Использовать Facebook Graph API вместо Instagram Graph API
        
        Returns:
            JSON ответ или None в случае ошибки
        """
        if not self.access_token:
            logger.error("[ERROR] Instagram Graph API: access_token не указан")
            return None
        
        # Для Facebook токенов используем Facebook Graph API
        # Для Instagram токенов (IGAAT) hashtag search НЕ работает - нужен Facebook токен (EAA)
        is_facebook_token = self.access_token.startswith('EAA')
        is_instagram_token = self.access_token.startswith('IGAAT') or self.access_token.startswith('IG')
        
        # Hashtag search работает ТОЛЬКО через Facebook Graph API с Facebook токеном
        if endpoint == 'ig_hashtag_search' or 'hashtag' in endpoint.lower():
            base_url = self.FACEBOOK_BASE_URL
            # Добавляем версию API для Facebook Graph API
            url = f"{base_url}/{self.API_VERSION}/{endpoint}"
        elif use_facebook_api or is_facebook_token:
            base_url = self.FACEBOOK_BASE_URL
            url = f"{base_url}/{self.API_VERSION}/{endpoint}"
        else:
            base_url = self.BASE_URL
            url = f"{base_url}/{endpoint}"
        
        if params is None:
            params = {}
        
        # Добавляем access_token если его нет в params
        if 'access_token' not in params:
            params['access_token'] = self.access_token
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, timeout=timeout, verify=True)
            else:
                response = self.session.post(url, json=params, timeout=timeout, verify=True)
            
            if response.status_code == 200:
                return response.json()
            else:
                error_data = response.json() if response.text else {}
                error_info = error_data.get('error', {})
                error_msg = error_info.get('message', 'Unknown error')
                error_code = error_info.get('code', response.status_code)
                error_type = error_info.get('type', 'Unknown')
                
                # Детальное логирование ошибок
                logger.warning(f"[WARN] Graph API {endpoint}: ошибка {error_code} ({error_type}): {error_msg}")
                
                # Специальная обработка для известных ошибок
                if error_code == 100:
                    if 'permissions' in error_msg.lower() or 'permission' in error_msg.lower():
                        logger.error("[ERROR] Проблема с разрешениями!")
                        logger.error("[ERROR] Убедитесь, что:")
                        logger.error("  1. Пройден App Review для 'Instagram Public Content Access'")
                        logger.error("  2. Токен имеет разрешение 'instagram_basic'")
                        logger.error("  3. Используется Facebook User access token (EAA...), а не Instagram токен (IGAAT...)")
                    elif 'does not exist' in error_msg.lower():
                        logger.error("[ERROR] Endpoint не существует или недоступен!")
                        logger.error("[ERROR] Возможные причины:")
                        logger.error("  1. Используется Instagram токен (IGAAT) вместо Facebook токена (EAA)")
                        logger.error("  2. Неправильная версия API")
                        logger.error("  3. Endpoint требует специальных разрешений")
                
                return None
                
        except requests.exceptions.SSLError as e:
            logger.error(f"[ERROR] Graph API {endpoint}: SSL ошибка: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[ERROR] Graph API {endpoint}: ошибка соединения: {e}")
            return None
        except Exception as e:
            logger.error(f"[ERROR] Graph API {endpoint}: неожиданная ошибка: {e}")
            return None
    
    def search_hashtag(self, hashtag: str) -> Optional[str]:
        """
        Найти ID хэштега по его названию.
        
        Согласно актуальной документации 2026:
        - Работает ТОЛЬКО с Facebook User access token (EAA...)
        - Instagram токены (IGAAT...) НЕ поддерживают hashtag search
        - Endpoint: GET /ig_hashtag_search?user_id=<<USER_ID>>&q=<<QUERY_STRING>>
        
        Args:
            hashtag: Название хэштега без #
        
        Returns:
            Hashtag ID или None в случае ошибки
        """
        # Проверяем тип токена
        is_facebook_token = self.access_token.startswith('EAA')
        is_instagram_token = self.access_token.startswith('IGAAT') or self.access_token.startswith('IG')
        
        if is_instagram_token:
            logger.error("[ERROR] Instagram токены (IGAAT...) НЕ поддерживают hashtag search!")
            logger.error("[ERROR] Для hashtag search нужен Facebook User access token (EAA...)")
            logger.error("[ERROR] Получите Facebook токен через Facebook Login в вашем приложении")
            return None
        
        if not is_facebook_token:
            logger.warning("[WARN] Неизвестный тип токена. Hashtag search работает только с Facebook токенами (EAA...)")
        
        # Получаем правильный Instagram User ID
        instagram_user_id = self._get_instagram_user_id()
        
        if not instagram_user_id:
            logger.error("[ERROR] Instagram Graph API: user_id не указан")
            return None
        
        logger.info(f"Ищу ID хэштега #{hashtag} через Facebook Graph API v{self.API_VERSION}...")
        
        # Согласно документации: GET /ig_hashtag_search?user_id=<<USER_ID>>&q=<<QUERY_STRING>>
        params = {
            'user_id': instagram_user_id,
            'q': hashtag
        }
        
        # Обязательно используем Facebook Graph API для hashtag search
        data = self._make_request('ig_hashtag_search', params=params, use_facebook_api=True)
        
        if not data:
            logger.warning(f"[WARN] Не удалось найти ID хэштега #{hashtag}")
            logger.warning("[WARN] Возможные причины:")
            logger.warning("  1. Требуется App Review для 'Instagram Public Content Access'")
            logger.warning("  2. Токен не имеет разрешения 'instagram_basic'")
            logger.warning("  3. Пользователь не одобрен для работы с Facebook Page")
            logger.warning("  4. Превышен лимит: максимум 30 уникальных хэштегов за 7 дней")
            return None
        
        # Парсим ответ согласно документации
        hashtag_id = None
        if 'data' in data and len(data['data']) > 0:
            hashtag_id = data['data'][0].get('id')
        elif 'id' in data:
            hashtag_id = data['id']
        
        if hashtag_id:
            logger.info(f"[OK] Найден ID хэштега #{hashtag}: {hashtag_id}")
        else:
            logger.warning(f"[WARN] Не найден ID для хэштега #{hashtag} в ответе API")
            logger.debug(f"[DEBUG] Ответ API: {data}")
        
        return hashtag_id
    
    def _get_instagram_user_id(self, force_refresh: bool = False) -> Optional[str]:
        """
        Получить Instagram Business Account ID (для Facebook токенов получает через Facebook Pages).
        
        Args:
            force_refresh: Принудительно обновить ID через /me
        
        Returns:
            Instagram Business Account ID или None
        """
        if not self.access_token:
            return self.user_id
        
        is_facebook_token = self.access_token.startswith('EAA')
        if is_facebook_token:
            # Для Facebook токена получаем Instagram Business Account ID через Facebook Pages
            # Instagram Business Account связан с Facebook Page, а не напрямую с User
            try:
                # Шаг 1: Получаем список страниц пользователя
                url = f"{self.FACEBOOK_BASE_URL}/me/accounts"
                params = {
                    'fields': 'id,name,instagram_business_account',
                    'access_token': self.access_token
                }
                
                response = self.session.get(url, params=params, timeout=30, verify=True)
                if response.status_code == 200:
                    data = response.json()
                    logger.debug(f"[DEBUG] Ответ /me/accounts: {data}")
                    if 'data' in data and len(data['data']) > 0:
                        logger.info(f"[INFO] Найдено {len(data['data'])} страниц Facebook")
                        # Ищем страницу с Instagram Business Account
                        for page in data['data']:
                            page_name = page.get('name', 'N/A')
                            page_id = page.get('id', 'N/A')
                            logger.debug(f"[DEBUG] Страница: {page_name} (ID: {page_id})")
                            if 'instagram_business_account' in page:
                                instagram_account = page['instagram_business_account']
                                if isinstance(instagram_account, dict) and 'id' in instagram_account:
                                    instagram_id = instagram_account['id']
                                    logger.info(f"[INFO] Найден Instagram Business Account ID: {instagram_id} (через страницу '{page_name}')")
                                    return instagram_id
                                else:
                                    logger.debug(f"[DEBUG] Страница '{page_name}' не имеет связанного Instagram Business Account")
                            else:
                                logger.debug(f"[DEBUG] Страница '{page_name}' не имеет поля instagram_business_account")
                    else:
                        logger.warning("[WARN] Не найдено страниц Facebook через /me/accounts")
                        logger.warning("[WARN] Возможные причины:")
                        logger.warning("  - У вас нет Facebook Pages")
                        logger.warning("  - Токен не имеет разрешения 'pages_show_list' или 'pages_read_engagement'")
                else:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                    error_code = error_data.get('error', {}).get('code', response.status_code)
                    logger.warning(f"[WARN] Ошибка получения страниц (код {error_code}): {error_msg}")
                
                # Шаг 2: Если не нашли через /me/accounts, пробуем проверить указанный user_id напрямую
                if self.user_id:
                    logger.info(f"[INFO] Проверяю указанный User ID: {self.user_id}")
                    # Пробуем получить информацию об этом ID как об Instagram Business Account
                    check_url = f"{self.FACEBOOK_BASE_URL}/{self.user_id}"
                    check_params = {
                        'fields': 'id,username,account_type',
                        'access_token': self.access_token
                    }
                    try:
                        check_response = self.session.get(check_url, params=check_params, timeout=30, verify=True)
                        if check_response.status_code == 200:
                            check_data = check_response.json()
                            logger.info(f"[INFO] Указанный ID валиден как Instagram Business Account")
                            logger.info(f"[INFO] Username: {check_data.get('username', 'N/A')}, Type: {check_data.get('account_type', 'N/A')}")
                            return self.user_id
                        else:
                            error_data = check_response.json() if check_response.text else {}
                            error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                            logger.warning(f"[WARN] Указанный ID не является валидным Instagram Business Account: {error_msg}")
                    except Exception as e:
                        logger.debug(f"[DEBUG] Ошибка проверки указанного ID: {e}")
                
                logger.warning("[WARN] Не найдено Instagram Business Account. Убедитесь, что:")
                logger.warning("  1. У вас есть Facebook Page")
                logger.warning("  2. Facebook Page связана с Instagram Business Account")
                logger.warning("  3. Токен имеет разрешение 'pages_read_engagement' или 'pages_show_list'")
                logger.warning("  4. INSTAGRAM_GRAPH_API_USER_ID содержит правильный Instagram Business Account ID")
                
            except Exception as e:
                logger.debug(f"[DEBUG] Ошибка получения Instagram User ID: {e}")
        
        return self.user_id
    
    def get_hashtag_top_media(
        self,
        hashtag_id: str,
        limit: int = 50,
        fields: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить топ посты по хэштегу.
        
        Args:
            hashtag_id: ID хэштега
            limit: Максимальное количество постов (макс. 50)
            fields: Поля для получения (по умолчанию: id,media_type,media_url,permalink,timestamp)
        
        Returns:
            Список постов
        """
        instagram_user_id = self._get_instagram_user_id()
        if not instagram_user_id:
            logger.error("[ERROR] Instagram Graph API: user_id не указан")
            return []
        
        # Согласно документации, обязательные поля: permalink для получения ссылок
        if fields is None:
            fields = 'id,media_type,media_url,permalink,timestamp,caption,comments_count,like_count'
        
        logger.info(f"Получаю топ посты для хэштега {hashtag_id}...")
        
        # Для Facebook токенов используем Facebook Graph API
        is_facebook_token = self.access_token.startswith('EAA')
        
        # Согласно документации: GET /{ig-hashtag-id}/top_media?user_id=<<IG_USER_ID>>&fields=...
        params = {
            'user_id': instagram_user_id,
            'fields': fields,
            'limit': min(limit, 50)  # Максимум 50 постов на страницу
        }
        
        # Обязательно используем Facebook Graph API для получения постов
        data = self._make_request(f"{hashtag_id}/top_media", params=params, use_facebook_api=True)
        
        if not data or 'data' not in data:
            if data and 'error' in data:
                error_msg = data['error'].get('message', 'Unknown error')
                error_code = data['error'].get('code', 'Unknown')
                logger.error(f"[ERROR] Ошибка получения топ постов (код {error_code}): {error_msg}")
            return []
        
        posts = data['data']
        logger.info(f"[OK] Получено {len(posts)} топ постов")
        
        # Обработка пагинации (если есть больше результатов)
        if 'paging' in data and 'next' in data['paging'] and len(posts) < limit:
            logger.debug(f"[DEBUG] Есть еще страницы результатов, но лимит {limit} достигнут")
        
        return posts
    
    def get_hashtag_recent_media(
        self,
        hashtag_id: str,
        limit: int = 50,
        fields: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить недавние посты по хэштегу (только последние 24 часа).
        
        Args:
            hashtag_id: ID хэштега
            limit: Максимальное количество постов (макс. 50)
            fields: Поля для получения (по умолчанию: id,media_type,media_url,permalink,timestamp)
        
        Returns:
            Список постов
        """
        instagram_user_id = self._get_instagram_user_id()
        if not instagram_user_id:
            logger.error("[ERROR] Instagram Graph API: user_id не указан")
            return []
        
        # Согласно документации, обязательные поля: permalink для получения ссылок
        if fields is None:
            fields = 'id,media_type,media_url,permalink,timestamp,caption,comments_count,like_count'
        
        logger.info(f"Получаю недавние посты для хэштега {hashtag_id} (только последние 24 часа)...")
        
        # Для Facebook токенов используем Facebook Graph API
        is_facebook_token = self.access_token.startswith('EAA')
        
        # Согласно документации: GET /{ig-hashtag-id}/recent_media?user_id=<<IG_USER_ID>>&fields=...
        # ВАЖНО: recent_media возвращает только посты за последние 24 часа!
        params = {
            'user_id': instagram_user_id,
            'fields': fields,
            'limit': min(limit, 50)  # Максимум 50 постов на страницу
        }
        
        # Обязательно используем Facebook Graph API для получения постов
        data = self._make_request(f"{hashtag_id}/recent_media", params=params, use_facebook_api=True)
        
        if not data or 'data' not in data:
            if data and 'error' in data:
                error_msg = data['error'].get('message', 'Unknown error')
                error_code = data['error'].get('code', 'Unknown')
                logger.error(f"[ERROR] Ошибка получения недавних постов (код {error_code}): {error_msg}")
            return []
        
        posts = data['data']
        logger.info(f"[OK] Получено {len(posts)} недавних постов (только за последние 24 часа)")
        
        # Обработка пагинации (если есть больше результатов)
        if 'paging' in data and 'next' in data['paging'] and len(posts) < limit:
            logger.debug(f"[DEBUG] Есть еще страницы результатов, но лимит {limit} достигнут")
        
        return posts
    
    def get_hashtag_posts(
        self,
        hashtag: str,
        limit: int = 50,
        include_recent: bool = True,
        include_top: bool = True
    ) -> List[str]:
        """
        Получить ссылки на посты по хэштегу.
        
        Args:
            hashtag: Название хэштега без #
            limit: Максимальное количество ссылок
            include_recent: Включать недавние посты (последние 24 часа)
            include_top: Включать топ посты
        
        Returns:
            Список URL постов
        """
        post_urls = []
        
        # Шаг 1: Ищем ID хэштега
        hashtag_id = self.search_hashtag(hashtag)
        if not hashtag_id:
            logger.warning(f"[WARN] Не удалось найти ID хэштега #{hashtag}")
            return post_urls
        
        # Шаг 2: Получаем посты
        if include_top:
            top_posts = self.get_hashtag_top_media(hashtag_id, limit=limit)
            for post in top_posts:
                permalink = post.get('permalink')
                if permalink and permalink not in post_urls:
                    post_urls.append(permalink)
                    if len(post_urls) >= limit:
                        break
        
        if len(post_urls) < limit and include_recent:
            recent_posts = self.get_hashtag_recent_media(hashtag_id, limit=limit)
            for post in recent_posts:
                permalink = post.get('permalink')
                if permalink and permalink not in post_urls:
                    post_urls.append(permalink)
                    if len(post_urls) >= limit:
                        break
        
        logger.info(f"[OK] Всего найдено {len(post_urls)} ссылок для #{hashtag}")
        return post_urls[:limit]
    
    def exchange_token(self, short_lived_token: Optional[str] = None) -> Optional[str]:
        """
        Обменять короткоживущий токен на долгоживущий (60 дней).
        
        Для Facebook токенов использует Facebook Graph API.
        
        Args:
            short_lived_token: Короткоживущий токен (если None, используется self.access_token)
        
        Returns:
            Долгоживущий токен или None в случае ошибки
        """
        if not self.app_secret:
            logger.error("[ERROR] Instagram Graph API: app_secret не указан для обмена токена")
            return None
        
        token = short_lived_token or self.access_token
        if not token:
            logger.error("[ERROR] Instagram Graph API: токен не указан")
            return None
        
        logger.info("Обмениваю токен на долгоживущий...")
        
        # Для Facebook токенов используем Facebook Graph API
        is_facebook_token = token.startswith('EAA')
        
        params = {
            'grant_type': 'ig_exchange_token',
            'client_secret': self.app_secret,
            'access_token': token
        }
        
        data = self._make_request('access_token', method='GET', params=params, use_facebook_api=is_facebook_token)
        
        if not data:
            # Проверяем, может токен уже долгоживущий или есть другая проблема
            logger.warning("[WARN] Не удалось обменять токен")
            logger.info("[INFO] Возможные причины:")
            logger.info("  - Токен уже долгоживущий (60 дней)")
            logger.info("  - Неверный App Secret")
            logger.info("  - Токен невалиден или истек")
            logger.info("  - Токен не является короткоживущим")
            return None
        
        if 'access_token' not in data:
            logger.error("[ERROR] Неожиданный формат ответа при обмене токена")
            return None
        
        long_lived_token = data['access_token']
        expires_in = data.get('expires_in', 0)
        
        logger.info(f"[OK] Токен обменян, срок действия: {expires_in} секунд (~{expires_in // 86400} дней)")
        return long_lived_token
    
    def debug_token(self) -> Optional[Dict[str, Any]]:
        """
        Проверить валидность и получить информацию о токене.
        
        Для проверки user access token требуется app access token.
        App access token = {app_id}|{app_secret}
        
        Returns:
            Информация о токене или None в случае ошибки
        """
        if not self.access_token:
            logger.error("[ERROR] Instagram Graph API: access_token не указан")
            return None
        
        logger.info("Проверяю валидность токена...")
        
        # Для debug_token нужен app access token (не user token)
        app_access_token = None
        if self.app_id and self.app_secret:
            app_access_token = f"{self.app_id}|{self.app_secret}"
        else:
            logger.warning("[WARN] App ID или App Secret не указаны, пробую без app access token...")
        
        params = {
            'input_token': self.access_token
        }
        
        # Добавляем app access token если есть
        if app_access_token:
            params['access_token'] = app_access_token
        
        # Используем Facebook Graph API для проверки токена
        url = "https://graph.facebook.com/debug_token"
        try:
            response = self.session.get(url, params=params, timeout=30, verify=True)
            if response.status_code == 200:
                data = response.json()
                logger.info("[OK] Токен валиден")
                return data
            else:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('error', {}).get('message', response.text)
                error_code = error_data.get('error', {}).get('code', 'Unknown')
                
                # Если ошибка из-за отсутствия app access token, это не критично
                if error_code == 100 and 'app access token' in error_msg.lower():
                    logger.info("[INFO] Токен работает (получение информации о пользователе успешно)")
                    logger.info("[INFO] Для полной проверки через debug_token нужен app access token")
                    return None
                else:
                    logger.warning(f"[WARN] Токен невалиден (код {error_code}): {error_msg}")
                    return None
        except Exception as e:
            logger.error(f"[ERROR] Ошибка проверки токена: {e}")
            return None
    
    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о пользователе Instagram.
        
        Если токен Facebook (EAA...), использует Facebook Graph API /me endpoint.
        
        Returns:
            Информация о пользователе или None в случае ошибки
        """
        if not self.access_token:
            logger.error("[ERROR] Instagram Graph API: access_token не указан")
            return None
        
        # Проверяем, это Facebook токен (EAA...) или Instagram токен (IG...)
        is_facebook_token = self.access_token.startswith('EAA')
        
        if is_facebook_token:
            # Для Facebook токена получаем информацию через Facebook Graph API
            logger.info("Использую Facebook Graph API /me endpoint...")
            url = f"{self.FACEBOOK_BASE_URL}/me"
            params = {
                'fields': 'id,name',
                'access_token': self.access_token
            }
            
            try:
                response = self.session.get(url, params=params, timeout=30, verify=True)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Пробуем получить Instagram Business Account через страницы
                    instagram_user_id = self._get_instagram_user_id()
                    if instagram_user_id:
                        # Получаем информацию об Instagram Business Account
                        instagram_url = f"{self.FACEBOOK_BASE_URL}/{instagram_user_id}"
                        instagram_params = {
                            'fields': 'id,username,account_type',
                            'access_token': self.access_token
                        }
                        instagram_response = self.session.get(instagram_url, params=instagram_params, timeout=30, verify=True)
                        if instagram_response.status_code == 200:
                            instagram_data = instagram_response.json()
                            data['instagram_id'] = instagram_data.get('id')
                            data['instagram_username'] = instagram_data.get('username')
                            data['instagram_account_type'] = instagram_data.get('account_type')
                    
                    logger.info("[OK] Информация о пользователе получена")
                    return data
                else:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                    logger.warning(f"[WARN] Не удалось получить информацию: {error_msg}")
                    return None
            except Exception as e:
                logger.error(f"[ERROR] Ошибка получения информации: {e}")
                return None
        else:
            # Для Instagram токена используем стандартный метод
            if not self.user_id:
                logger.error("[ERROR] Instagram Graph API: user_id не указан")
                return None
            
            logger.info(f"Получаю информацию о пользователе {self.user_id}...")
            
            params = {
                'fields': 'id,username,account_type'
            }
            
            data = self._make_request(self.user_id, params=params)
            
            if data:
                logger.info("[OK] Информация о пользователе получена")
            else:
                    logger.warning("[WARN] Не удалось получить информацию о пользователе")
            
            return data
    
    def get_user_media(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        fields: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить посты конкретного пользователя Instagram.
        
        Работает с Instagram токенами (IGAAT...) и Facebook токенами (EAA...).
        Endpoint: GET /{ig-user-id}/media
        
        Args:
            user_id: Instagram User ID (если None, используется self.user_id)
            limit: Максимальное количество постов (макс. 50)
            fields: Поля для получения
        
        Returns:
            Список постов пользователя
        """
        instagram_user_id = user_id or self._get_instagram_user_id()
        if not instagram_user_id:
            logger.error("[ERROR] Instagram Graph API: user_id не указан")
            return []
        
        if fields is None:
            fields = 'id,media_type,media_url,permalink,timestamp,caption,comments_count,like_count'
        
        logger.info(f"Получаю посты пользователя {instagram_user_id}...")
        
        # Определяем тип токена
        is_facebook_token = self.access_token.startswith('EAA')
        
        # Endpoint: GET /{ig-user-id}/media
        params = {
            'fields': fields,
            'limit': min(limit, 50)
        }
        
        # Для Instagram токенов используем Instagram Graph API
        # Для Facebook токенов используем Facebook Graph API
        use_facebook_api = is_facebook_token
        data = self._make_request(f"{instagram_user_id}/media", params=params, use_facebook_api=use_facebook_api)
        
        if not data or 'data' not in data:
            if data and 'error' in data:
                error_msg = data['error'].get('message', 'Unknown error')
                error_code = data['error'].get('code', 'Unknown')
                logger.error(f"[ERROR] Ошибка получения постов пользователя (код {error_code}): {error_msg}")
            return []
        
        posts = data['data']
        logger.info(f"[OK] Получено {len(posts)} постов пользователя")
        
        # Обработка пагинации
        if 'paging' in data and 'next' in data['paging'] and len(posts) < limit:
            logger.debug(f"[DEBUG] Есть еще страницы результатов, но лимит {limit} достигнут")
        
        return posts
    
    def get_user_media_urls(
        self,
        user_id: Optional[str] = None,
        limit: int = 50
    ) -> List[str]:
        """
        Получить ссылки на посты конкретного пользователя Instagram.
        
        Работает с Instagram токенами (IGAAT...) и Facebook токенами (EAA...).
        
        Args:
            user_id: Instagram User ID (если None, используется self.user_id)
            limit: Максимальное количество ссылок
        
        Returns:
            Список URL постов
        """
        posts = self.get_user_media(user_id=user_id, limit=limit)
        post_urls = []
        
        for post in posts:
            permalink = post.get('permalink')
            if permalink and permalink not in post_urls:
                post_urls.append(permalink)
                if len(post_urls) >= limit:
                    break
        
        logger.info(f"[OK] Получено {len(post_urls)} ссылок на посты пользователя")
        return post_urls[:limit]
