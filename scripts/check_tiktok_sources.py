"""Проверка TikTok-источников и имён тем."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from database.models import Base
from config import settings

e = create_engine(settings.DATABASE_URL)
Base.metadata.create_all(e)
with e.connect() as c:
    r = c.execute(text("""
        SELECT cs.id, cs.source_type, t.id as tid, t.name
        FROM content_sources cs
        JOIN topics t ON t.id = cs.topic_id
        WHERE cs.source_type = 'tiktok'
    """))
    for row in r:
        d = dict(row._mapping)
        name = d.get("name") or ""
        d["name_repr"] = repr(name)
        d["name_hex"] = name.encode("utf-8").hex()[:80]
        print(d)
