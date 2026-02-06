"""
АВТОМАТИЧЕСКАЯ расшифровка cookies из Яндекс браузера.
Читает cookies из SQLite базы и расшифровывает их через Windows DPAPI.
РАБОТАЕТ ДАЖЕ ЕСЛИ БРАУЗЕР ОТКРЫТ!
"""
import os
import json
import sqlite3
import base64
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
import requests

try:
    import win32crypt
    from Cryptodome.Cipher import AES
    DECRYPT_AVAILABLE = True
except ImportError:
    DECRYPT_AVAILABLE = False
    logger.warning("pywin32 или pycryptodomex не установлены. Установите: pip install pywin32 pycryptodomex")


def get_yandex_encryption_key() -> Optional[bytes]:
    """
    Получить ключ шифрования из Local State файла Яндекс браузера.
    
    Returns:
        Расшифрованный ключ или None
    """
    if not DECRYPT_AVAILABLE:
        return None
    
    try:
        # Путь к Local State файлу
        local_state_path = Path(os.getenv("LOCALAPPDATA")) / "Yandex" / "YandexBrowser" / "User Data" / "Local State"
        
        if not local_state_path.exists():
            logger.warning(f"Local State файл не найден: {local_state_path}")
            return None
        
        # Читаем Local State
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
        
        # Извлекаем зашифрованный ключ
        encrypted_key = local_state.get('os_crypt', {}).get('encrypted_key')
        if not encrypted_key:
            logger.warning("Ключ шифрования не найден в Local State")
            return None
        
        # Декодируем из Base64
        encrypted_key_bytes = base64.b64decode(encrypted_key)
        
        # Убираем префикс "DPAPI" (первые 5 байт)
        encrypted_key_bytes = encrypted_key_bytes[5:]
        
        # Расшифровываем через DPAPI
        try:
            key = win32crypt.CryptUnprotectData(encrypted_key_bytes, None, None, None, 0)[1]
            logger.info("✅ Ключ шифрования успешно расшифрован")
            return key
        except Exception as e:
            logger.error(f"Ошибка расшифровки ключа: {e}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка получения ключа шифрования: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None


def decrypt_cookie_value(encrypted_value: bytes, key: bytes) -> Optional[str]:
    """
    Расшифровать значение cookie через AES-GCM.
    
    Args:
        encrypted_value: Зашифрованное значение
        key: Ключ шифрования
    
    Returns:
        Расшифрованное значение или None
    """
    if not DECRYPT_AVAILABLE:
        return None
    
    try:
        # Chrome использует префикс v10 (версия 10)
        if encrypted_value[:3] != b'v10':
            # Старый формат или не зашифровано
            try:
                return encrypted_value.decode('utf-8')
            except:
                return None
        
        # Извлекаем компоненты
        # Формат: v10 (3 байта) + nonce (12 байт) + ciphertext + tag (16 байт)
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:-16]
        tag = encrypted_value[-16:]
        
        # Расшифровываем через AES-GCM
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        
        return decrypted.decode('utf-8')
        
    except Exception as e:
        logger.debug(f"Ошибка расшифровки cookie: {e}")
        return None


def get_yandex_cookies_from_db(session: requests.Session) -> bool:
    """
    АВТОМАТИЧЕСКИ получить и расшифровать cookies из Яндекс браузера.
    РАБОТАЕТ ДАЖЕ ЕСЛИ БРАУЗЕР ОТКРЫТ!
    
    Args:
        session: Сессия requests
    
    Returns:
        True если cookies успешно получены
    """
    if not DECRYPT_AVAILABLE:
        logger.error("pywin32 или pycryptodomex не установлены")
        logger.info("Установите: pip install pywin32 pycryptodomex")
        return False
    
    try:
        logger.info("="*80)
        logger.info("АВТОМАТИЧЕСКАЯ РАСШИФРОВКА COOKIES ИЗ ЯНДЕКС БРАУЗЕРА")
        logger.info("="*80)
        
        # Получаем ключ шифрования
        logger.info("\nШаг 1: Получаю ключ шифрования...")
        key = get_yandex_encryption_key()
        if not key:
            logger.error("❌ Не удалось получить ключ шифрования")
            return False
        
        # Путь к базе cookies
        cookies_db_path = Path(os.getenv("LOCALAPPDATA")) / "Yandex" / "YandexBrowser" / "User Data" / "Default" / "Network" / "Cookies"
        
        if not cookies_db_path.exists():
            logger.error(f"❌ Файл cookies не найден: {cookies_db_path}")
            return False
        
        logger.info(f"✅ Найден файл cookies: {cookies_db_path}")
        
        # Пробуем несколько способов чтения базы
        logger.info("\nШаг 2: Читаю cookies из базы...")
        
        # Способ 1: Прямое чтение через SQLite с флагом immutable (readonly)
        cookie_rows = None
        try:
            logger.info("Попытка 1: Прямое чтение через SQLite (readonly)...")
            conn = sqlite3.connect(f'file:{cookies_db_path}?mode=ro&immutable=1', uri=True)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name, encrypted_value, host_key, path, expires_utc, is_secure, is_httponly
                FROM cookies
                WHERE host_key LIKE '%instagram.com%'
            """)
            
            cookie_rows = cursor.fetchall()
            conn.close()
            logger.info(f"✅ Прямое чтение сработало! Найдено {len(cookie_rows)} cookies")
        except Exception as e:
            logger.debug(f"Прямое чтение не сработало: {e}")
            cookie_rows = None
        
        # Способ 2: Копирование базы
        if cookie_rows is None:
            logger.info("Попытка 2: Копирование базы для чтения...")
            temp_db = Path(tempfile.gettempdir()) / f"yandex_cookies_decrypt_{os.getpid()}.db"
            
            copied = False
            import time
            
            # Пробуем закрыть браузер автоматически для копирования
            logger.info("Пробую временно закрыть браузер для копирования файла...")
            try:
                import psutil
                yandex_procs = []
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'] and 'yandex' in proc.info['name'].lower():
                            yandex_procs.append(proc)
                    except:
                        pass
                
                if yandex_procs:
                    logger.info(f"Найдено {len(yandex_procs)} процессов Яндекс браузера")
                    logger.info("Временно закрываю для копирования файла...")
                    
                    # Сохраняем пути к exe для перезапуска
                    yandex_exe_paths = []
                    for proc in yandex_procs:
                        try:
                            exe_path = proc.exe()
                            if exe_path:
                                yandex_exe_paths.append(exe_path)
                            proc.terminate()
                        except:
                            pass
                    
                    # Ждем закрытия
                    logger.info("Жду закрытия браузера (3 секунды)...")
                    time.sleep(3)
                    
                    # Принудительно убиваем если не закрылись
                    for proc in yandex_procs:
                        try:
                            if proc.is_running():
                                logger.info("Принудительно закрываю процесс...")
                                proc.kill()
                        except:
                            pass
                    
                    # Ждем еще
                    time.sleep(2)
                    
                    # Пробуем скопировать несколько раз
                    for copy_attempt in range(5):
                        try:
                            shutil.copy2(cookies_db_path, temp_db)
                            copied = True
                            logger.info(f"✅ База скопирована после закрытия браузера (попытка {copy_attempt + 1})")
                            break
                        except PermissionError:
                            if copy_attempt < 4:
                                logger.debug(f"Файл еще заблокирован, жду... (попытка {copy_attempt + 1})")
                                time.sleep(1)
                                continue
                            else:
                                logger.warning("Файл все еще заблокирован после закрытия браузера")
                                logger.info("Возможно другой процесс использует файл")
                                break
                        except Exception as e:
                            logger.debug(f"Ошибка копирования: {e}")
                            break
                    
                    # Запускаем браузер обратно
                    if copied:
                        logger.info("Запускаю браузер обратно...")
                        try:
                            # Используем сохраненные пути или стандартный путь
                            if yandex_exe_paths:
                                yandex_exe = yandex_exe_paths[0]
                            else:
                                yandex_exe = Path(os.getenv("LOCALAPPDATA")) / "Yandex" / "YandexBrowser" / "Application" / "browser.exe"
                            
                            if Path(yandex_exe).exists():
                                import subprocess
                                subprocess.Popen([str(yandex_exe)], creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
                                logger.info("✅ Браузер запущен обратно")
                        except Exception as e:
                            logger.debug(f"Не удалось запустить браузер обратно: {e}")
                else:
                    logger.info("Браузер не запущен, пробую копировать напрямую...")
                    try:
                        shutil.copy2(cookies_db_path, temp_db)
                        copied = True
                        logger.info("✅ База скопирована")
                    except Exception as e:
                        logger.debug(f"Ошибка копирования: {e}")
                        
            except ImportError:
                # psutil не установлен - пробуем обычное копирование
                logger.info("psutil не установлен, пробую обычное копирование...")
                for attempt in range(10):
                    try:
                        time.sleep(0.5 * (attempt + 1))
                        shutil.copy2(cookies_db_path, temp_db)
                        copied = True
                        logger.info(f"✅ База скопирована (попытка {attempt + 1})")
                        break
                    except PermissionError:
                        if attempt < 9:
                            continue
                        else:
                            logger.warning("❌ Не удалось скопировать базу")
                            logger.info("РЕШЕНИЕ: Установите psutil (pip install psutil) для автоматического закрытия браузера")
                            logger.info("Или закройте браузер вручную на 2 секунды")
                            return False
            except Exception as e:
                logger.debug(f"Ошибка автоматического закрытия: {e}")
                # Пробуем обычное копирование
                for attempt in range(5):
                    try:
                        time.sleep(0.5)
                        shutil.copy2(cookies_db_path, temp_db)
                        copied = True
                        logger.info(f"✅ База скопирована (попытка {attempt + 1})")
                        break
                    except PermissionError:
                        if attempt < 4:
                            continue
                        else:
                            return False
            
            if copied:
                try:
                    conn = sqlite3.connect(str(temp_db))
                    cursor = conn.cursor()
            
                    # Читаем cookies для Instagram
                    cursor.execute("""
                        SELECT name, encrypted_value, host_key, path, expires_utc, is_secure, is_httponly
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
                    
                    logger.info(f"✅ Найдено {len(cookie_rows)} cookies в базе")
                except Exception as e:
                    logger.error(f"❌ Ошибка чтения скопированной базы: {e}")
                    try:
                        temp_db.unlink(missing_ok=True)
                    except:
                        pass
                    return False
        
        if not cookie_rows:
            logger.warning("❌ Cookies Instagram не найдены в базе")
            logger.info("Убедитесь что вы залогинены на instagram.com в Яндекс браузере")
            return False
        
        # Расшифровываем cookies
        logger.info("\nШаг 4: Расшифровываю cookies...")
        decrypted_count = 0
        
        for row in cookie_rows:
            name, encrypted_value, host_key = row[0], row[1], row[2]
            
            # Расшифровываем значение
            if isinstance(encrypted_value, bytes):
                decrypted_value = decrypt_cookie_value(encrypted_value, key)
            else:
                # Если уже строка, используем как есть
                decrypted_value = str(encrypted_value)
            
            if decrypted_value:
                # Загружаем в сессию
                domain = host_key
                if domain.startswith('.'):
                    domain = domain[1:]
                
                session.cookies.set(name, decrypted_value, domain=domain)
                decrypted_count += 1
        
        logger.info(f"✅ Расшифровано и загружено {decrypted_count} cookies")
        
        # Проверяем важные cookies
        important = ['sessionid', 'csrftoken', 'ds_user_id']
        found = [name for name in important if name in session.cookies]
        logger.info(f"✅ Найдено важных cookies: {', '.join(found)}")
        
        if 'sessionid' in session.cookies:
            logger.info("✅✅✅ sessionid найден! Cookies готовы к использованию!")
            return True
        else:
            logger.warning("⚠️  sessionid не найден")
            logger.warning("Убедитесь что вы залогинены на instagram.com")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения cookies: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False
