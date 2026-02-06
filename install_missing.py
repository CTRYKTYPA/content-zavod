"""Установка недостающих зависимостей."""
import subprocess
import sys

print("🔧 Установка недостающих зависимостей...")
print("")

# Список пакетов для установки
packages = [
    "moviepy",
    "opencv-python",
    "Pillow",
    "numpy"
]

for package in packages:
    print(f"Установка {package}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✅ {package} установлен")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Ошибка установки {package}: {e}")
        print("   Попробуйте установить вручную: pip install", package)

print("")
print("✅ Готово!")
print("Попробуйте снова: python simple_test.py")
