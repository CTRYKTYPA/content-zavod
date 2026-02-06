"""Добавить данные авторизации Instagram в .env."""
import sys
from pathlib import Path

# Устанавливаем UTF-8 для вывода
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Данные для добавления
username = "Rise_motivation.7"
password = "Qw1234567!s1"

env_file = Path(".env")

# Читаем существующий файл
if env_file.exists():
    content = env_file.read_text(encoding="utf-8")
    lines = content.split("\n")
else:
    lines = []

# Обновляем или добавляем строки
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

# Добавляем если не найдены
if not username_found:
    updated_lines.append(f"INSTAGRAM_USERNAME={username}")
if not password_found:
    updated_lines.append(f"INSTAGRAM_PASSWORD={password}")

# Сохраняем
env_file.write_text("\n".join(updated_lines), encoding="utf-8")

print("OK: Данные авторизации Instagram добавлены в .env")
print(f"   Логин: {username}")
print("\nТеперь можно запустить тест:")
print("   python test_download.py")
