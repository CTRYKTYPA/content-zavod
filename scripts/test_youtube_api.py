#!/usr/bin/env python3
"""
Проверка YouTube Data API v3: поиск и загрузка/выкладка видео.

API key даёт:
  - Поиск (search.list) — работает
  - Метаданные (videos.list) — работает

API key НЕ даёт:
  - Скачивание файла видео — YouTube API этого не умеет вообще
  - Загрузку (videos.insert) — нужен OAuth 2.0, не API key
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests
from config import settings

API_KEY = settings.YOUTUBE_API_KEY
BASE = "https://www.googleapis.com/youtube/v3"


def main():
    if not API_KEY:
        print("YOUTUBE_API_KEY не задан в .env")
        return 1

    print("=== 1. Поиск (search.list) — должно работать с API key ===\n")
    r = requests.get(
        f"{BASE}/search",
        params={
            "part": "snippet",
            "q": "shorts мотивация",
            "type": "video",
            "maxResults": 3,
            "key": API_KEY,
        },
        timeout=10,
    )
    if r.status_code != 200:
        print(f"Ошибка: {r.status_code}")
        print(r.text[:500])
        return 1

    data = r.json()
    items = data.get("items") or []
    print(f"Найдено: {len(items)} видео\n")

    video_ids = []
    for it in items:
        vid = it.get("id", {}).get("videoId")
        if not vid:
            continue
        video_ids.append(vid)
        title = (it.get("snippet", {}).get("title") or "")[:60]
        safe = title.encode("ascii", "replace").decode("ascii")
        print(f"  {vid}: {safe}...")

    if not video_ids:
        print("Нет videoId в ответе")
        return 0

    print("\n=== 2. Метаданные (videos.list) — должно работать с API key ===\n")
    r2 = requests.get(
        f"{BASE}/videos",
        params={
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids[:1]),
            "key": API_KEY,
        },
        timeout=10,
    )
    if r2.status_code != 200:
        print(f"Ошибка: {r2.status_code}")
        print(r2.text[:500])
        return 1

    v = (r2.json().get("items") or [{}])[0]
    snippet = v.get("snippet", {})
    stats = v.get("statistics", {})
    details = v.get("contentDetails", {})
    print(f"  Длительность: {details.get('duration', '?')}")
    print(f"  Просмотры: {stats.get('viewCount', '?')}")
    print(f"  Лайки: {stats.get('likeCount', '?')}")

    print("\n=== 3. Скачивание файла видео ===")
    print("  YouTube API НЕ предоставляет URL или поток для скачивания.")
    print("  API даёт только метаданные (id, название, статистика).")
    print("  Для скачивания нужен yt-dlp (неофициально).")

    print("\n=== 4. Загрузка видео на YouTube (videos.insert) ===")
    print("  Нужен OAuth 2.0 (вход пользователя), не API key.")
    print("  API key — только для чтения (поиск, метаданные).")
    print("  Для публикации: настроить OAuth, получить refresh_token.")

    print("\n[OK] API key работает: поиск и метаданные — ок.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
