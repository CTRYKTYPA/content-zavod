"""
Этап 1 — setup: 5 тем, YouTube Shorts как источник.
Создаёт темы, источники с хэштегами (20 на тему), min_likes=10k, min_views=500k.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from loguru import logger

from database.models import Base, Topic, ContentSource
from config import settings
from youtube_themes_config import YOUTUBE_THEMES, DEFAULT_MIN_LIKES, DEFAULT_MIN_VIEWS


def setup_youtube_stage1() -> None:
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    for th in YOUTUBE_THEMES:
        topic = db.query(Topic).filter(Topic.name == th["name"]).first()
        if not topic:
            topic = Topic(
                name=th["name"],
                description=th.get("description", ""),
                is_active=True,
                branding_enabled=True,
            )
            db.add(topic)
            db.commit()
            db.refresh(topic)
            logger.info(f"Создана тема: {th['name']} (id={topic.id})")
        else:
            logger.info(f"Тема уже есть: {th['name']} (id={topic.id})")

        existing = db.query(ContentSource).filter(
            ContentSource.topic_id == topic.id,
            ContentSource.source_type == "youtube_shorts",
        ).first()

        source_value = json.dumps({
            "hashtags": th["hashtags"],
            "min_duration": 10,
            "max_duration": 120,
        })
        if existing:
            existing.source_value = source_value
            existing.min_likes = DEFAULT_MIN_LIKES
            existing.min_views = DEFAULT_MIN_VIEWS
            existing.is_active = True
            db.commit()
            logger.info(f"  Обновлён источник YouTube Shorts для {th['name']}")
        else:
            src = ContentSource(
                topic_id=topic.id,
                source_type="youtube_shorts",
                source_value=source_value,
                min_likes=DEFAULT_MIN_LIKES,
                min_views=DEFAULT_MIN_VIEWS,
                is_active=True,
            )
            db.add(src)
            db.commit()
            logger.info(f"  Добавлен источник YouTube Shorts для {th['name']}")

        for sub in ("downloads", "processed"):
            d = Path(sub) / th["folder"]
            d.mkdir(parents=True, exist_ok=True)

    db.close()
    logger.info("Setup Этапа 1 (YouTube) завершён.")


if __name__ == "__main__":
    setup_youtube_stage1()
