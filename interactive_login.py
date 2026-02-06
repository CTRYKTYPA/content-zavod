"""Интерактивный вход в Instagram через instaloader."""
import sys
import codecs
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import settings
import instaloader

print("=" * 60)
print("ИНТЕРАКТИВНЫЙ ВХОД В INSTAGRAM")
print("=" * 60)

username = settings.INSTAGRAM_USERNAME
password = settings.INSTAGRAM_PASSWORD

if not username:
    print("Ошибка: INSTAGRAM_USERNAME не указан в .env")
    exit(1)

print(f"\nЛогин: {username}")
print("\nЭтот способ обходит checkpoint через интерактивный вход.")
print("Instaloader откроет браузер и вы войдёте через него.\n")

try:
    L = instaloader.Instaloader()
    
    # Пробуем сначала загрузить существующую сессию
    try:
        from instaloader.instaloader import get_default_session_filename
        session_file = get_default_session_filename(username)
        if Path(session_file).exists():
            print("Найдена сохранённая сессия, пробую загрузить...")
            L.load_session_from_file(username)
            test_user = L.test_login()
            if test_user:
                print(f"OK: Сессия работает! Пользователь: {test_user}")
                exit(0)
    except:
        pass
    
    # Интерактивный вход
    print("Запускаю интерактивный вход...")
    print("Откроется браузер, войдите через него.\n")
    
    if password:
        # Пробуем сначала обычный вход
        try:
            print("Пробую войти с паролем...")
            L.login(username, password)
            print("OK: Успешный вход!")
            L.save_session_to_file()
            print("OK: Сессия сохранена!")
            exit(0)
        except Exception as e:
            error_msg = str(e)
            if "Checkpoint" in error_msg or "checkpoint" in error_msg.lower():
                print("Требуется checkpoint, переключаюсь на интерактивный вход...")
            else:
                print(f"Ошибка: {e}")
                print("Переключаюсь на интерактивный вход...")
    
    # Интерактивный вход (откроет браузер)
    print("\nОткрываю браузер для интерактивного входа...")
    print("Войдите в Instagram через открывшийся браузер.")
    print("После входа закройте это окно или нажмите Ctrl+C.\n")
    
    L.interactive_login(username)
    
    # Проверяем что вход успешен
    test_user = L.test_login()
    if test_user:
        print(f"\nOK: Успешный вход! Пользователь: {test_user}")
        L.save_session_to_file()
        print("OK: Сессия сохранена!")
        print("\nТеперь можно запускать систему:")
        print("  python test_download.py")
    else:
        print("\nОшибка: Не удалось войти")
        
except KeyboardInterrupt:
    print("\n\nПрервано пользователем")
except Exception as e:
    print(f"\nОшибка: {e}")
    import traceback
    traceback.print_exc()
    
    print("\nАльтернативное решение:")
    print("1. Войдите в Instagram через обычный браузер")
    print("2. Запустите: python fix_auth_simple.py")
