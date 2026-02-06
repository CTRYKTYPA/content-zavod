"""
Этап 1 — setup: темы + TikTok как источник (users / hashtags).
Создаёт темы при необходимости, добавляет источники tiktok. Без API — yt-dlp.
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
from tiktok_themes_config import (
    TIKTOK_THEMES,
    DEFAULT_MIN_LIKES,
    DEFAULT_MIN_VIEWS,
    MIN_DURATION,
    MAX_DURATION,
)


def setup_tiktok_stage1() -> None:
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    for th in TIKTOK_THEMES:
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
            ContentSource.source_type == "tiktok",
        ).first()

        source_value = json.dumps({
            "users": th.get("users") or [],
            "hashtags": th.get("hashtags") or [],
            "min_duration": MIN_DURATION,
            "max_duration": MAX_DURATION,
        })
        if existing:
            existing.source_value = source_value
            existing.min_likes = DEFAULT_MIN_LIKES
            existing.min_views = DEFAULT_MIN_VIEWS
            existing.is_active = True
            db.commit()
            logger.info(f"  Обновлён источник TikTok для {th['name']}")
        else:
            src = ContentSource(
                topic_id=topic.id,
                source_type="tiktok",
                source_value=source_value,
                min_likes=DEFAULT_MIN_LIKES,
                min_views=DEFAULT_MIN_VIEWS,
                is_active=True,
            )
            db.add(src)
            db.commit()
            logger.info(f"  Добавлен источник TikTok для {th['name']}")

        for sub in ("downloads", "processed"):
            d = ROOT / sub / th["folder"]
            d.mkdir(parents=True, exist_ok=True)

    db.close()
    logger.info("Setup Этапа 1 (TikTok) завершён.")


if __name__ == "__main__":
    setup_tiktok_stage1()
