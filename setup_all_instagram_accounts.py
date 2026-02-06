"""Массовая настройка всех Instagram аккаунтов для сбора контента."""
import sys
import codecs
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database import init_db, get_db
from database.models import Account, PlatformType, Topic
import instaloader

print("=" * 60)
print("НАСТРОЙКА ВСЕХ INSTAGRAM АККАУНТОВ")
print("=" * 60)
print("\nЭтот скрипт настроит сессии для всех Instagram аккаунтов")
print("используемых для сбора контента.\n")

# Инициализация БД
init_db()
db = next(get_db())

try:
    # Получаем все тематики
    topics = db.query(Topic).all()
    if not topics:
        print("Ошибка: Тематики не найдены!")
        print("Сначала запустите: python create_topics.py")
        exit(1)
    
    print(f"Найдено тематик: {len(topics)}\n")
    
    # Проверяем установлен ли browser-cookie3
    try:
        import browser_cookie3
    except ImportError:
        print("Устанавливаю browser-cookie3...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "browser-cookie3"])
        import browser_cookie3
    
    print("Инструкция:")
    print("1. Откройте браузер (Chrome/Firefox/Edge)")
    print("2. Войдите ВО ВСЕ Instagram аккаунты которые будут использоваться")
    print("3. Можно использовать разные вкладки или разные браузеры")
    print("4. Убедитесь что все аккаунты залогинены")
    print()
    
    input("Нажмите Enter когда все аккаунты будут залогинены в браузере...")
    
    # Пробуем импортировать все сессии из браузера
    print("\nИщу сессии в браузерах...")
    
    browsers = [
        ("Chrome", lambda: browser_cookie3.chrome(domain_name="instagram.com")),
        ("Firefox", lambda: browser_cookie3.firefox(domain_name="instagram.com")),
        ("Edge", lambda: browser_cookie3.edge(domain_name="instagram.com")),
    ]
    
    imported_sessions = {}
    
    for browser_name, get_cookies in browsers:
        try:
            cookies = get_cookies()
            if not cookies:
                continue
            
            print(f"\nНайдены cookies в {browser_name}")
            
            # Создаём временный instaloader для проверки
            L = instaloader.Instaloader()
            
            # Импортируем cookies
            import requests
            session = requests.Session()
            for cookie in cookies:
                session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
            
            L.context._session = session
            
            # Проверяем какие пользователи залогинены
            test_user = L.test_login()
            if test_user:
                print(f"  OK: Найдена сессия для {test_user}")
                
                # Сохраняем сессию
                L.save_session_to_file()
                imported_sessions[test_user.lower()] = test_user
                print(f"  OK: Сессия сохранена")
        
        except Exception as e:
            print(f"  Пропуск {browser_name}: {e}")
            continue
    
    if not imported_sessions:
        print("\nОшибка: Не найдено ни одной сессии Instagram в браузерах")
        print("Убедитесь что:")
        print("  - Вы залогинены в Instagram через браузер")
        print("  - Браузер не закрыт")
        exit(1)
    
    print(f"\nИмпортировано сессий: {len(imported_sessions)}")
    print("Аккаунты:", ", ".join(imported_sessions.values()))
    
    # Распределяем аккаунты по тематикам
    print("\nНастраиваю аккаунты в базе данных...")
    
    session_usernames = list(imported_sessions.values())
    created_count = 0
    updated_count = 0
    
    for i, topic in enumerate(topics):
        # Распределяем аккаунты по кругу (можно использовать один для всех)
        session_username = session_usernames[i % len(session_usernames)]
        
        # Ищем существующий аккаунт для этой тематики
        account = db.query(Account).filter(
            Account.topic_id == topic.id,
            Account.platform == PlatformType.PLATFORM_C
        ).first()
        
        if not account:
            # Создаём новый аккаунт
            account = Account(
                topic_id=topic.id,
                platform=PlatformType.PLATFORM_C,
                username=f"{topic.name.lower()}_collector",
                instagram_session_username=session_username,
                is_active=True
            )
            db.add(account)
            created_count += 1
            print(f"  Тематика '{topic.name}': аккаунт {session_username}")
        else:
            # Обновляем сессию
            if account.instagram_session_username != session_username:
                account.instagram_session_username = session_username
                updated_count += 1
                print(f"  Тематика '{topic.name}': обновлён на {session_username}")
            else:
                print(f"  Тематика '{topic.name}': уже настроен ({session_username})")
    
    db.commit()
    
    print(f"\nOK: Создано аккаунтов: {created_count}")
    print(f"OK: Обновлено аккаунтов: {updated_count}")
    
    print("\n" + "=" * 60)
    print("НАСТРОЙКА ЗАВЕРШЕНА!")
    print("=" * 60)
    print("\nВсе Instagram аккаунты настроены и готовы к работе.")
    print("Система будет автоматически использовать сохранённые сессии.")
    print("\nТеперь можно запускать систему:")
    print("  python run.py")

except Exception as e:
    print(f"\nОшибка: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

finally:
    db.close()
