"""Настройка авторизации Instagram."""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("НАСТРОЙКА АВТОРИЗАЦИИ INSTAGRAM")
print("=" * 60)
print("\nДля работы с хэштегами Instagram требует авторизацию.")
print("Вам понадобятся логин и пароль от аккаунта Instagram.\n")

# Проверяем .env файл
env_file = Path(".env")
env_content = ""

if env_file.exists():
    env_content = env_file.read_text(encoding="utf-8")
    print("📄 Файл .env найден")
else:
    print("📄 Создаю файл .env...")

# Запрашиваем данные
print("\nВведите данные для авторизации:")
username = input("Логин Instagram: ").strip()
password = input("Пароль Instagram: ").strip()

if not username or not password:
    print("\n❌ Логин и пароль обязательны!")
    exit(1)

# Обновляем или добавляем строки в .env
lines = env_content.split("\n") if env_content else []
updated_lines = []
username_found = False
password_found = False

for line in lines:
    if line.startswith("INSTAGRAM_USERNAME="):
        updated_lines.append(f"INSTAGRAM_USERNAME={username}")
        username_found = True
    elif line.startswith("INSTAGRAM_PASSWORD="):
        updated_lines.append(f"INSTAGRAM_PASSWORD={password}")
        password_found = True
    else:
        updated_lines.append(line)

if not username_found:
    updated_lines.append(f"INSTAGRAM_USERNAME={username}")
if not password_found:
    updated_lines.append(f"INSTAGRAM_PASSWORD={password}")

# Сохраняем
env_content = "\n".join(updated_lines)
env_file.write_text(env_content, encoding="utf-8")

print(f"\n✅ Данные сохранены в .env")
print(f"   Логин: {username}")
print(f"\n💡 При первом запуске система попросит подтвердить вход")
print("   (может потребоваться код из SMS/приложения для 2FA)")

print("\n" + "=" * 60)
print("Теперь можно запустить тест:")
print("  python test_download.py")
print("=" * 60)
