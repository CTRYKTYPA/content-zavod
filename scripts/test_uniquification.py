"""
Тест уникализации: скачать один Short, наложить плашку, сохранить в processed/uniquification_test/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import settings
from database.models import Topic
from modules.video_processor import VideoProcessor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Использовать готовое видео или скачать одно
SAMPLE = ROOT / "downloads" / "humor" / "BvNJfAJgnVq.mp4"
OUT_DIR = ROOT / "processed" / "uniquification_test"
OUT_PATH = OUT_DIR / "sample_plashka.mp4"


def main():
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    topic = db.query(Topic).filter(Topic.name == "Юмор").first()
    if not topic:
        # Создаём минимальную тему для теста
        from database.models import Base
        Base.metadata.create_all(engine)
        topic = Topic(name="Юмор", description="Тест", is_active=True, branding_enabled=True)
        db.add(topic)
        db.commit()
        db.refresh(topic)

    db.close()

    if not SAMPLE.exists():
        print(f"Видео не найдено: {SAMPLE}")
        print("Скачайте Short в downloads/humor/ или укажите другой путь в скрипте.")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proc = VideoProcessor(topic)
    ok, err = proc.process_video(str(SAMPLE), str(OUT_PATH), remove_watermarks=False)
    if ok:
        print(f"Готово: {OUT_PATH}")
        print("Откройте файл и посмотрите плашку внизу (название темы).")
    else:
        print(f"Ошибка: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
