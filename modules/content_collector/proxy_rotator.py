"""Ротация прокси для эмуляции разных IP."""
import random
from typing import Optional, List
from loguru import logger
from config import settings


class ProxyRotator:
    """Ротатор прокси для эмуляции разных IP адресов."""
    
    def __init__(self):
        """Инициализация ротатора прокси."""
        self.proxies: List[str] = []
        self.current_index = 0
        
        # Загружаем прокси из настроек
        if settings.INSTAGRAM_PROXY:
            # Если указано несколько через запятую
            if ',' in settings.INSTAGRAM_PROXY:
                self.proxies = [p.strip() for p in settings.INSTAGRAM_PROXY.split(',')]
            else:
                self.proxies = [settings.INSTAGRAM_PROXY]
        
        # Добавляем из списка
        if settings.PROXY_LIST:
            self.proxies.extend(settings.PROXY_LIST)
        
        # Удаляем дубликаты
        self.proxies = list(dict.fromkeys(self.proxies))
        
        if self.proxies:
            logger.info(f"Загружено прокси для ротации: {len(self.proxies)}")
            if len(self.proxies) == 1:
                logger.warning("Используется только один прокси - ротация IP не будет работать")
                logger.info("Рекомендуется добавить несколько прокси для эмуляции разных IP")
    
    def get_next_proxy(self) -> Optional[str]:
        """Получить следующий прокси (ротация)."""
        if not self.proxies:
            return None
        
        if settings.ROTATE_PROXIES:
            # Случайный выбор
            proxy = random.choice(self.proxies)
        else:
            # По кругу
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
        
        return proxy
    
    def get_random_proxy(self) -> Optional[str]:
        """Получить случайный прокси."""
        if not self.proxies:
            return None
        return random.choice(self.proxies)
    
    def has_proxies(self) -> bool:
        """Проверить есть ли прокси."""
        return len(self.proxies) > 0


# Глобальный экземпляр ротатора
_rotator = None

def get_proxy_rotator() -> ProxyRotator:
    """Получить глобальный ротатор прокси."""
    global _rotator
    if _rotator is None:
        _rotator = ProxyRotator()
    return _rotator
